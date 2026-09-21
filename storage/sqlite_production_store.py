from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


MAX_SCOPE_COMPONENT_LENGTH = 256
MAX_RECORD_ID_LENGTH = 256
MAX_RECORD_PAYLOAD_BYTES = 256 * 1024


class SQLiteProductionStore:
    """Durable provider-neutral production store with tenant+subject isolation.

    The tenant and subject are part of every primary-key lookup. Callers cannot
    load or list another scope merely by knowing a record identifier.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._path = Path(path)
        self._lock = RLock()
        self._reject_symlinked_database()
        self._initialize()

    def _reject_symlinked_database(self) -> None:
        try:
            parent = self._path.parent
            if parent.resolve(strict=True) != parent.absolute():
                raise RuntimeError("production database directory cannot be a symbolic link")
            if self._path.exists():
                stat = self._path.lstat()
                if self._path.is_symlink() or not self._path.is_file():
                    raise RuntimeError("production database must be a regular file")
        except OSError as exc:
            raise RuntimeError("production database could not be inspected") from exc

    def _connect(self) -> sqlite3.Connection:
        self._reject_symlinked_database()
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        parent = self._path.parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlinked_database()
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
        try:
            self._path.chmod(0o600)
        except OSError as exc:
            raise RuntimeError("production storage permissions could not be hardened") from exc

    @staticmethod
    def _component(value: str, field: str, *, maximum: int = MAX_SCOPE_COMPONENT_LENGTH) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} is required")
        if len(normalized) > maximum:
            raise ValueError(f"{field} exceeds the maximum length")
        return normalized

    @classmethod
    def _require_scope(cls, tenant_id: str, subject_id: str) -> tuple[str, str]:
        return (
            cls._component(tenant_id, "tenant_id"),
            cls._component(subject_id, "subject_id"),
        )

    @classmethod
    def _record_id(cls, record: dict[str, Any]) -> str:
        if not isinstance(record, dict):
            raise ValueError("record must be a dictionary")
        raw = record.get("record_id") or record.get("decision_id") or ""
        return cls._component(str(raw), "record_id", maximum=MAX_RECORD_ID_LENGTH)

    @staticmethod
    def _encode_record(record: dict[str, Any]) -> str:
        try:
            payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("production record is not safely serializable") from exc
        if len(payload.encode("utf-8")) > MAX_RECORD_PAYLOAD_BYTES:
            raise ValueError("production record exceeds the maximum size")
        return payload

    def save(self, record: dict[str, Any], *, tenant_id: str, subject_id: str) -> None:
        tenant, subject = self._require_scope(tenant_id, subject_id)
        record_id = self._record_id(record)
        payload = self._encode_record(record)
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
        key = self._component(record_id, "record_id", maximum=MAX_RECORD_ID_LENGTH)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM production_records WHERE tenant_id = ? AND subject_id = ? AND record_id = ?",
                (tenant, subject, key),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError, RecursionError) as exc:
            raise RuntimeError("production record is corrupt") from exc

    def list(self, *, tenant_id: str, subject_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        tenant, subject = self._require_scope(tenant_id, subject_id)
        if limit is not None:
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 10_000:
                raise ValueError("limit must be between 1 and 10000 when provided")
        query = (
            "SELECT payload FROM production_records "
            "WHERE tenant_id = ? AND subject_id = ? "
            "ORDER BY updated_at DESC, record_id DESC"
        )
        params: tuple[Any, ...] = (tenant, subject)
        if limit is not None:
            query += " LIMIT ?"
            params = (tenant, subject, limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        decoded: list[dict[str, Any]] = []
        for row in rows:
            try:
                decoded.append(json.loads(row["payload"]))
            except (TypeError, json.JSONDecodeError, RecursionError) as exc:
                raise RuntimeError("production record is corrupt") from exc
        return decoded
