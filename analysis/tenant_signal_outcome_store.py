"""Persist directional outcome labels against previously audited tenant signals."""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from analysis.signal_outcome_resolver import resolve_next_candle_direction_safe
from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
from security.tenant_context import TenantContext


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
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
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

    def list_outcomes(self, context: TenantContext) -> list[dict[str, Any]]:
        if not isinstance(context, TenantContext):
            raise PermissionError("trusted tenant context is required")
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
