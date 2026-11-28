"""Tenant-scoped immutable ledger for strategy selection and holdout evaluation.

The ledger records experiment provenance; it does not calculate profitability,
approve strategies, or turn an evidence score into a win probability.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _metrics(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("metrics must be a non-empty mapping")
    normalized: dict[str, float | int | bool | str | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 80:
            raise ValueError("metric names must be non-empty text up to 80 characters")
        if isinstance(item, bool) or item is None or isinstance(item, str):
            if isinstance(item, str) and len(item) > 240:
                raise ValueError("metric text values are limited to 240 characters")
            normalized[key.strip()] = item
        elif isinstance(item, (int, float)):
            import math
            if not math.isfinite(float(item)):
                raise ValueError("metrics must not contain NaN or infinity")
            normalized[key.strip()] = item
        else:
            raise ValueError("metrics must contain only scalar values")
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)


class TenantStrategyTrialLedger:
    """Append-only, tenant-isolated record of selection trials and one holdout."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_strategy_trials (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    phase TEXT NOT NULL CHECK(phase IN ('SELECTION', 'HOLDOUT')),
                    strategy_version TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    dataset_fingerprint TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject_id, experiment_id, trial_id)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy_trials_experiment
                ON tenant_strategy_trials
                (tenant_id, subject_id, experiment_id, phase, evaluated_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _validate_identity(experiment_id: str, trial_id: str, strategy_version: str,
                           dataset_id: str, fingerprint: str) -> None:
        for name, value in (
            ("experiment_id", experiment_id), ("trial_id", trial_id),
            ("strategy_version", strategy_version), ("dataset_id", dataset_id),
        ):
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
                raise ValueError(f"{name} must be non-empty text up to 160 characters")
        if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("dataset_fingerprint must be a lowercase SHA-256 hex digest")

    def _record(self, context: TenantContext, *, phase: str, experiment_id: str,
                trial_id: str, strategy_version: str, dataset_id: str,
                dataset_fingerprint: str, window_start: str, window_end: str,
                evaluated_at: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
        owner = require_tenant_context(context)
        self._validate_identity(experiment_id, trial_id, strategy_version, dataset_id, dataset_fingerprint)
        start = _timestamp(window_start, "window_start")
        end = _timestamp(window_end, "window_end")
        evaluated = _timestamp(evaluated_at, "evaluated_at")
        if start >= end or end > evaluated:
            raise ValueError("evaluation window must be ordered and end no later than evaluated_at")
        metrics_json = _metrics(metrics)
        payload = {
            "phase": phase, "strategy_version": strategy_version.strip(),
            "dataset_id": dataset_id.strip(), "dataset_fingerprint": dataset_fingerprint,
            "window_start": start, "window_end": end, "evaluated_at": evaluated,
            "metrics_json": metrics_json,
        }
        record_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT phase, strategy_version, dataset_id, dataset_fingerprint,
                   window_start, window_end, evaluated_at, metrics_json, record_hash
                   FROM tenant_strategy_trials
                   WHERE tenant_id=? AND subject_id=? AND experiment_id=?""",
                (owner.tenant_id, owner.subject_id, experiment_id.strip()),
            ).fetchall()
            existing = db.execute(
                """SELECT record_hash, phase FROM tenant_strategy_trials
                   WHERE tenant_id=? AND subject_id=? AND experiment_id=? AND trial_id=?""",
                (owner.tenant_id, owner.subject_id, experiment_id.strip(), trial_id.strip()),
            ).fetchone()
            if existing is not None:
                if existing["record_hash"] != record_hash or existing["phase"] != phase:
                    raise ValueError("trial_id already exists with different immutable evidence")
                return {"experiment_id": experiment_id.strip(), "trial_id": trial_id.strip(),
                        "phase": phase, "status": "ALREADY_RECORDED", "record_hash": record_hash}
            if phase == "SELECTION":
                if any(row["phase"] == "HOLDOUT" for row in rows):
                    raise ValueError("selection is frozen after holdout evaluation")
            else:
                if any(row["phase"] == "HOLDOUT" for row in rows):
                    raise ValueError("an experiment may have only one immutable holdout evaluation")
                selection = [row for row in rows if row["phase"] == "SELECTION"]
                if not selection:
                    raise ValueError("holdout evaluation requires at least one recorded selection trial")
                if any(row["dataset_fingerprint"] == dataset_fingerprint for row in selection):
                    raise ValueError("holdout dataset fingerprint must differ from selection data")
            db.execute(
                """INSERT INTO tenant_strategy_trials
                   (tenant_id, subject_id, experiment_id, trial_id, phase, strategy_version,
                    dataset_id, dataset_fingerprint, window_start, window_end, evaluated_at,
                    metrics_json, record_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (owner.tenant_id, owner.subject_id, experiment_id.strip(), trial_id.strip(),
                 phase, payload["strategy_version"], payload["dataset_id"], dataset_fingerprint,
                 start, end, evaluated, metrics_json, record_hash),
            )
            selection_count = sum(row["phase"] == "SELECTION" for row in rows) + (phase == "SELECTION")
        return {"experiment_id": experiment_id.strip(), "trial_id": trial_id.strip(),
                "phase": phase, "status": "RECORDED", "selection_trial_count": selection_count,
                "record_hash": record_hash}

    def record_selection_trial(self, context: TenantContext, **record: Any) -> dict[str, Any]:
        return self._record(context, phase="SELECTION", **record)

    def record_holdout_evaluation(self, context: TenantContext, **record: Any) -> dict[str, Any]:
        return self._record(context, phase="HOLDOUT", **record)

    def list_experiment(self, context: TenantContext, experiment_id: str) -> list[dict[str, Any]]:
        owner = require_tenant_context(context)
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError("experiment_id is required")
        with self._connect() as db:
            rows = db.execute(
                """SELECT trial_id, phase, strategy_version, dataset_id, dataset_fingerprint,
                   window_start, window_end, evaluated_at, metrics_json, record_hash
                   FROM tenant_strategy_trials
                   WHERE tenant_id=? AND subject_id=? AND experiment_id=?
                   ORDER BY CASE phase WHEN 'SELECTION' THEN 0 ELSE 1 END, evaluated_at, trial_id""",
                (owner.tenant_id, owner.subject_id, experiment_id.strip()),
            ).fetchall()
        return [{
            "trial_id": row["trial_id"], "phase": row["phase"],
            "strategy_version": row["strategy_version"], "dataset_id": row["dataset_id"],
            "dataset_fingerprint": row["dataset_fingerprint"],
            "window_start": row["window_start"], "window_end": row["window_end"],
            "evaluated_at": row["evaluated_at"], "metrics": json.loads(row["metrics_json"]),
            "record_hash": row["record_hash"],
        } for row in rows]
