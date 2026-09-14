from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


class SQLiteProductionStore:
    """Durable provider-neutral production store with tenant+subject isolation.

    The tenant and subject are part of every primary-key lookup. Callers cannot
    load or list another scope merely by knowing a record identifier.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        parent = Path(self.path).parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS production_records (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, subject_id, record_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_production_records_scope_time "
                "ON production_records (tenant_id, subject_id, updated_at, record_id)"
            )
            connection.commit()

    @staticmethod
    def _require_scope(tenant_id: str, subject_id: str) -> tuple[str, str]:
        tenant = str(tenant_id).strip()
        subject = str(subject_id).strip()
        if not tenant or not subject:
            raise ValueError("tenant_id and subject_id are required")
        return tenant, subject

    @staticmethod
    def _record_id(record: dict[str, Any]) -> str:
        record_id = str(record.get("record_id") or record.get("decision_id") or "").strip()
        if not record_id:
            raise ValueError("record_id or decision_id is required")
        return record_id

    def save(self, record: dict[str, Any], *, tenant_id: str, subject_id: str) -> None:
        tenant, subject = self._require_scope(tenant_id, subject_id)
        record_id = self._record_id(record)
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO production_records (tenant_id, subject_id, record_id, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, subject_id, record_id)
                DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
                """,
                (tenant, subject, record_id, payload),
            )
            connection.commit()

    def load(self, record_id: str, *, tenant_id: str, subject_id: str) -> dict[str, Any] | None:
        tenant, subject = self._require_scope(tenant_id, subject_id)
        key = str(record_id).strip()
        if not key:
            raise ValueError("record_id is required")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM production_records WHERE tenant_id = ? AND subject_id = ? AND record_id = ?",
                (tenant, subject, key),
            ).fetchone()
        return json.loads(row["payload"]) if row is not None else None

    def list(self, *, tenant_id: str, subject_id: str, limit: int = 100) -> list[dict[str, Any]]:
        tenant, subject = self._require_scope(tenant_id, subject_id)
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM production_records
                WHERE tenant_id = ? AND subject_id = ?
                ORDER BY updated_at DESC, record_id DESC
                LIMIT ?
                """,
                (tenant, subject, int(limit)),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
