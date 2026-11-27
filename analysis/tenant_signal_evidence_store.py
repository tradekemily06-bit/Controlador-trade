"""Tenant-scoped audit of technical signal evidence, never probability forecasts.

This store records what the analyzer actually emitted at decision time. It is
intentionally separate from probability calibration: an evidence score such as
75/100 is not a 75% chance of profit.
"""
from __future__ import annotations

import sqlite3
from math import isfinite
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.timeframes import normalize_timeframe
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_ALLOWED_DIRECTIONS = {"COMPRA", "VENDA", "AGUARDAR"}
_ALLOWED_PROVENANCE = {"REAL_MARKET_DATA"}


def _utc(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _owner(context: TenantContext) -> TenantContext:
    return require_tenant_context(context)


class TenantSignalEvidenceStore:
    """Append-only technical-signal snapshots isolated by tenant and subject."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_signal_evidence (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    source_id TEXT NOT NULL DEFAULT 'UNSCOPED',
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    evidence_score REAL NOT NULL,
                    score_semantics TEXT NOT NULL,
                    candle_close_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject_id, signal_id)
                )
            """)
            existing_columns = {row[1] for row in db.execute("PRAGMA table_info(tenant_signal_evidence)").fetchall()}
            if "source_id" not in existing_columns:
                db.execute("ALTER TABLE tenant_signal_evidence ADD COLUMN source_id TEXT NOT NULL DEFAULT 'UNSCOPED'")
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant_signal_evidence_context
                ON tenant_signal_evidence
                (tenant_id, subject_id, symbol, timeframe, observed_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def record_signal(
        self,
        context: TenantContext,
        *,
        signal_id: str,
        symbol: str,
        timeframe: str,
        direction: str,
        model_version: str,
        evidence_score: float,
        score_semantics: str,
        candle_close_at: str,
        observed_at: str,
        valid_until: str,
        provenance: str,
        source_id: str = "UNSCOPED",
    ) -> dict[str, Any]:
        owner = _owner(context)
        required = (signal_id, symbol, timeframe, direction, model_version, score_semantics)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("signal identity and context are required")
        canonical_direction = direction.strip().upper()
        if canonical_direction not in _ALLOWED_DIRECTIONS:
            raise ValueError("direction must be COMPRA, VENDA or AGUARDAR")
        if isinstance(evidence_score, bool) or not isinstance(evidence_score, (int, float)):
            raise ValueError("evidence_score must be numeric")
        try:
            evidence_score_value = float(evidence_score)
        except (OverflowError, ValueError) as exc:
            raise ValueError("evidence_score must be finite and between 0 and 100") from exc
        if not isfinite(evidence_score_value) or not 0 <= evidence_score_value <= 100:
            raise ValueError("evidence_score must be finite and between 0 and 100")
        if score_semantics != "EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY":
            raise ValueError("technical score semantics must be explicit")
        if provenance not in _ALLOWED_PROVENANCE:
            raise ValueError("only verified real market data may be audited")
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id.strip()) > 160:
            raise ValueError("source_id must identify the provider connection")
        canonical_timeframe = normalize_timeframe(timeframe)
        closed = _utc(candle_close_at, "candle_close_at")
        observed = _utc(observed_at, "observed_at")
        expiry = _utc(valid_until, "valid_until")
        if datetime.fromisoformat(closed) > datetime.fromisoformat(observed):
            raise ValueError("analysis cannot precede the closed candle")
        if datetime.fromisoformat(expiry) <= datetime.fromisoformat(observed):
            raise ValueError("signal validity must end after observation")
        expected = (
            source_id.strip(), signal_id.strip(), symbol.strip().upper(),
            canonical_timeframe, canonical_direction, model_version.strip(),
            evidence_score_value, score_semantics, closed, observed, expiry, provenance,
        )
        with self._connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO tenant_signal_evidence
                (tenant_id, subject_id, source_id, signal_id, symbol, timeframe, direction,
                 model_version, evidence_score, score_semantics, candle_close_at,
                 observed_at, valid_until, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (owner.tenant_id, owner.subject_id, *expected),
            )
            row = db.execute(
                """SELECT source_id, signal_id, symbol, timeframe, direction,
                model_version, evidence_score, score_semantics, candle_close_at,
                observed_at, valid_until, provenance
                FROM tenant_signal_evidence
                WHERE tenant_id=? AND subject_id=? AND signal_id=?""",
                (owner.tenant_id, owner.subject_id, signal_id.strip()),
            ).fetchone()
            if row is None:
                raise RuntimeError("signal evidence insert could not be verified")
            actual = tuple(row[key] for key in (
                "source_id", "signal_id", "symbol", "timeframe", "direction",
                "model_version", "evidence_score", "score_semantics",
                "candle_close_at", "observed_at", "valid_until", "provenance",
            ))
            if actual != expected:
                raise ValueError("signal_id already exists with different immutable evidence")
            audit_status = "RECORDED" if db.total_changes else "ALREADY_RECORDED"
        return {
            "signal_id": signal_id.strip(),
            "timeframe": canonical_timeframe,
            "audit_status": audit_status,
            "score_type": "EVIDENCE_STRENGTH",
            "probability_of_profit": None,
            "outcome_status": "NOT_RESOLVED",
        }

    def list_signals(
        self,
        context: TenantContext,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[dict[str, Any]]:
        owner = _owner(context)
        clauses = ["tenant_id = ?", "subject_id = ?"]
        params: list[Any] = [owner.tenant_id, owner.subject_id]
        if symbol is not None:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbol filter must be non-empty text")
            clauses.append("symbol = ?")
            params.append(symbol.strip().upper())
        if timeframe is not None:
            clauses.append("timeframe = ?")
            params.append(normalize_timeframe(timeframe))
        with self._connect() as db:
            rows = db.execute(
                "SELECT signal_id, source_id, symbol, timeframe, direction, model_version, "
                "evidence_score, score_semantics, candle_close_at, observed_at, "
                "valid_until, provenance FROM tenant_signal_evidence WHERE "
                + " AND ".join(clauses) + " ORDER BY observed_at ASC",
                params,
            ).fetchall()
        return [dict(row) | {
            "score_type": "EVIDENCE_STRENGTH",
            "probability_of_profit": None,
        } for row in rows]
