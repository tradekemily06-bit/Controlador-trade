"""Persist directional outcome labels against previously audited tenant signals."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from analysis.signal_outcome_resolver import resolve_next_candle_direction_safe
from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class TenantSignalOutcomeStore:
    """Resolve and persist one immutable real-market directional label per signal.

    The same TenantSignalEvidenceStore instance/database must be supplied so
    signal evidence and its outcome share one local transaction boundary.
    """

    def __init__(self, evidence_store: TenantSignalEvidenceStore) -> None:
        if not isinstance(evidence_store, TenantSignalEvidenceStore):
            raise TypeError("evidence_store must be TenantSignalEvidenceStore")
        self.evidence_store = evidence_store
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_signal_outcomes (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    outcome INTEGER,
                    outcome_status TEXT NOT NULL,
                    outcome_definition TEXT NOT NULL,
                    candle_open_at TEXT,
                    candle_close_at TEXT,
                    provenance TEXT NOT NULL,
                    net_profit_status TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject_id, signal_id),
                    FOREIGN KEY (tenant_id, subject_id, signal_id)
                    REFERENCES tenant_signal_evidence(tenant_id, subject_id, signal_id)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.evidence_store.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def resolve(
        self,
        context: TenantContext,
        signal_id: str,
        candle: Mapping[str, Any],
        *,
        provenance: str,
    ) -> dict[str, Any]:
        context = require_tenant_context(context)
        if not isinstance(signal_id, str) or not signal_id.strip():
            raise ValueError("signal_id is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT signal_id, symbol, timeframe, direction, model_version,
                evidence_score, score_semantics, candle_close_at, observed_at,
                valid_until, provenance FROM tenant_signal_evidence
                WHERE tenant_id=? AND subject_id=? AND signal_id=?""",
                (context.tenant_id, context.subject_id, signal_id.strip()),
            ).fetchone()
            if row is None:
                raise LookupError("signal not found in tenant scope")
            existing = db.execute(
                """SELECT signal_id FROM tenant_signal_outcomes
                WHERE tenant_id=? AND subject_id=? AND signal_id=?""",
                (context.tenant_id, context.subject_id, signal_id.strip()),
            ).fetchone()
            if existing is not None:
                raise ValueError("signal outcome is immutable once resolved")
            result = resolve_next_candle_direction_safe(
                dict(row), candle, provenance=provenance
            )
            db.execute(
                """INSERT INTO tenant_signal_outcomes
                (tenant_id, subject_id, signal_id, outcome, outcome_status,
                 outcome_definition, candle_open_at, candle_close_at,
                 provenance, net_profit_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context.tenant_id, context.subject_id, result["signal_id"],
                    None if result["outcome"] is None else int(result["outcome"]),
                    result["outcome_status"], result["outcome_definition"],
                    result["candle_open_at"], result["candle_close_at"],
                    result["provenance"], result["net_profit_status"],
                ),
            )
        return result

    def resolve_pending_for_candle(
        self,
        context: TenantContext,
        *,
        source_id: str,
        candle: Mapping[str, Any],
        provenance: str,
    ) -> list[dict[str, Any]]:
        """Resolve only pending signals whose next candle is this exact bar.

        Source identity is mandatory so one broker account's candle cannot
        resolve another account's signal, even for the same tenant/symbol.
        """
        context = require_tenant_context(context)
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is required")
        symbol = candle.get("symbol")
        timeframe = candle.get("timeframe")
        open_time = candle.get("open_time")
        if not all(isinstance(value, str) and value.strip() for value in (symbol, timeframe, open_time)):
            raise ValueError("candle identity and open_time are required")
        from data.timeframes import normalize_timeframe
        canonical_timeframe = normalize_timeframe(timeframe)
        try:
            parsed_open = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("candle open_time must be a valid ISO-8601 timestamp") from exc
        if parsed_open.tzinfo is None:
            raise ValueError("candle open_time must include timezone")
        canonical_open_time = parsed_open.astimezone(timezone.utc).isoformat()
        with self._connect() as db:
            rows = db.execute(
                """SELECT e.signal_id FROM tenant_signal_evidence e
                LEFT JOIN tenant_signal_outcomes o
                  ON o.tenant_id=e.tenant_id AND o.subject_id=e.subject_id
                 AND o.signal_id=e.signal_id
                WHERE e.tenant_id=? AND e.subject_id=? AND e.source_id=?
                  AND e.symbol=? AND e.timeframe=? AND e.candle_close_at=?
                  AND e.direction IN ('COMPRA', 'VENDA')
                  AND o.signal_id IS NULL
                ORDER BY e.observed_at ASC""",
                (
                    context.tenant_id, context.subject_id, source_id.strip(),
                    symbol.strip().upper(), canonical_timeframe, canonical_open_time,
                ),
            ).fetchall()
        resolved = []
        for row in rows:
            try:
                resolved.append(self.resolve(
                    context, row["signal_id"], candle, provenance=provenance
                ))
            except ValueError as exc:
                if "immutable once resolved" not in str(exc):
                    raise
        return resolved

    def list_outcomes(self, context: TenantContext) -> list[dict[str, Any]]:
        context = require_tenant_context(context)
        with self._connect() as db:
            rows = db.execute(
                """SELECT signal_id, outcome, outcome_status, outcome_definition,
                candle_open_at, candle_close_at, provenance, net_profit_status
                FROM tenant_signal_outcomes
                WHERE tenant_id=? AND subject_id=?
                ORDER BY candle_close_at ASC""",
                (context.tenant_id, context.subject_id),
            ).fetchall()
        return [{
            "signal_id": row["signal_id"],
            "outcome": None if row["outcome"] is None else bool(row["outcome"]),
            "outcome_status": row["outcome_status"],
            "outcome_definition": row["outcome_definition"],
            "candle_open_at": row["candle_open_at"],
            "candle_close_at": row["candle_close_at"],
            "provenance": row["provenance"],
            "net_profit_status": row["net_profit_status"],
            "probability_of_profit": None,
            "calibration_eligible": False,
        } for row in rows]
