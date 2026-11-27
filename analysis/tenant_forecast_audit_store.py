"""Tenant-scoped, append-first audit storage for probability forecasts.

This local SQLite implementation is a development/single-host foundation.
It is not a production shared database and never approves or emits a probability.
"""
from __future__ import annotations

import sqlite3
from math import isfinite
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.timeframes import normalize_timeframe
from security.tenant_context import TenantContext


_ALLOWED_PROVENANCE = {"REAL_MARKET_DATA", "VERIFIED_REAL_EXECUTION"}


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _owner(context: TenantContext) -> TenantContext:
    if not isinstance(context, TenantContext):
        raise PermissionError("trusted tenant context is required")
    for value in (context.tenant_id, context.subject_id):
        if not isinstance(value, str) or not value.strip():
            raise PermissionError("trusted tenant context is invalid")
    return context


class TenantForecastAuditStore:
    """Persist forecast-before-outcome evidence within tenant/subject scope."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_probability_forecasts (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    forecast_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    probability REAL NOT NULL,
                    forecast_at TEXT NOT NULL,
                    resolved_at TEXT,
                    outcome INTEGER,
                    provenance TEXT,
                    PRIMARY KEY (tenant_id, subject_id, forecast_id)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant_probability_context
                ON tenant_probability_forecasts
                (tenant_id, subject_id, symbol, timeframe, direction, model_version, forecast_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def record_forecast(
        self,
        context: TenantContext,
        *,
        forecast_id: str,
        symbol: str,
        timeframe: str,
        direction: str,
        model_version: str,
        probability: float,
        forecast_at: str,
    ) -> dict[str, Any]:
        owner = _owner(context)
        if not all(isinstance(x, str) and x.strip() for x in (
            forecast_id, symbol, timeframe, direction, model_version
        )):
            raise ValueError("forecast identifiers and context are required")
        if direction.strip().upper() not in {"COMPRA", "VENDA"}:
            raise ValueError("direction must be COMPRA or VENDA")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError("probability must be numeric")
        try:
            probability_value = float(probability)
        except (OverflowError, ValueError) as exc:
            raise ValueError("probability must be finite and between 0 and 1") from exc
        if not isfinite(probability_value) or not 0.0 <= probability_value <= 1.0:
            raise ValueError("probability must be finite and between 0 and 1")
        timestamp = _utc(forecast_at).isoformat()
        canonical_timeframe = normalize_timeframe(timeframe)
        with self._connect() as db:
            db.execute(
                """INSERT INTO tenant_probability_forecasts
                (tenant_id, subject_id, forecast_id, symbol, timeframe, direction,
                 model_version, probability, forecast_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    owner.tenant_id, owner.subject_id, forecast_id.strip(),
                    symbol.strip().upper(), canonical_timeframe,
                    direction.strip().upper(), model_version.strip(),
                    probability_value, timestamp,
                ),
            )
        return {
            "forecast_id": forecast_id.strip(),
            "timeframe": canonical_timeframe,
            "recorded_before_outcome": True,
            "calibration_status": "PENDING_OUTCOME",
        }

    def resolve_forecast(
        self,
        context: TenantContext,
        forecast_id: str,
        *,
        outcome: bool,
        resolved_at: str,
        provenance: str,
    ) -> dict[str, Any]:
        owner = _owner(context)
        if not isinstance(forecast_id, str) or not forecast_id.strip():
            raise ValueError("forecast_id is required")
        if not isinstance(outcome, bool):
            raise ValueError("outcome must be boolean")
        if not isinstance(provenance, str) or provenance not in _ALLOWED_PROVENANCE:
            raise ValueError("outcome provenance is not eligible for calibration")
        resolved = _utc(resolved_at).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT forecast_at, resolved_at FROM tenant_probability_forecasts
                WHERE tenant_id=? AND subject_id=? AND forecast_id=?""",
                (owner.tenant_id, owner.subject_id, forecast_id.strip()),
            ).fetchone()
            if row is None:
                raise LookupError("forecast not found in tenant scope")
            if row["resolved_at"] is not None:
                raise ValueError("forecast outcome is immutable once resolved")
            if _utc(row["forecast_at"]) >= _utc(resolved):
                raise ValueError("outcome resolution must follow the forecast")
            db.execute(
                """UPDATE tenant_probability_forecasts
                SET resolved_at=?, outcome=?, provenance=?
                WHERE tenant_id=? AND subject_id=? AND forecast_id=?
                AND resolved_at IS NULL""",
                (
                    resolved, int(outcome), provenance,
                    owner.tenant_id, owner.subject_id, forecast_id.strip(),
                ),
            )
        return {"forecast_id": forecast_id.strip(), "resolved": True}

    def calibration_forecasts(self, context: TenantContext) -> list[Any]:
        """Return resolved, tenant-scoped records in the evaluator's strict type."""
        from analysis.probability_calibration import ProbabilityForecast

        return [
            ProbabilityForecast(**record)
            for record in self.calibration_records(context)
        ]

    def calibration_records(self, context: TenantContext) -> list[dict[str, Any]]:
        owner = _owner(context)
        with self._connect() as db:
            rows = db.execute(
                """SELECT forecast_id, symbol, timeframe, direction, model_version,
                probability, outcome, forecast_at, resolved_at, provenance
                FROM tenant_probability_forecasts
                WHERE tenant_id=? AND subject_id=? AND resolved_at IS NOT NULL
                ORDER BY forecast_at ASC""",
                (owner.tenant_id, owner.subject_id),
            ).fetchall()
        return [{
            "forecast_id": row["forecast_id"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "direction": row["direction"],
            "model_version": row["model_version"],
            "probability": float(row["probability"]),
            "outcome": bool(row["outcome"]),
            "forecast_at": row["forecast_at"],
            "resolved_at": row["resolved_at"],
            "provenance": row["provenance"],
            "out_of_sample": True,
        } for row in rows]
