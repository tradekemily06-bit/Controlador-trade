from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock


MAX_SCOPE_COMPONENT_LENGTH = 256
MAX_NAMESPACE_LENGTH = 128
MAX_PAYLOAD_BYTES = 256 * 1024


class SQLiteScopedStateStore:
    """Small durable JSON state store keyed by tenant, subject and namespace.

    This is a single-instance provider. It is deliberately not presented as a
    distributed SaaS database; multi-instance deployments must use a shared
    provider before production is enabled.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = RLock()
        self._reject_symlinked_database()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlinked_database()
        with self._lock, sqlite3.connect(self.database_path) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scoped_state ("
                "tenant_id TEXT NOT NULL, subject_id TEXT NOT NULL, "
                "namespace TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY (tenant_id, subject_id, namespace))"
            )
            db.commit()
        try:
            self.database_path.chmod(0o600)
        except OSError as exc:
            raise RuntimeError("scoped state storage permissions could not be hardened") from exc

    def _reject_symlinked_database(self) -> None:
        try:
            if self.database_path.is_symlink():
                raise RuntimeError("scoped state database cannot be a symbolic link")
        except OSError as exc:
            raise RuntimeError("scoped state database could not be inspected") from exc

    @staticmethod
    def _component(value: str | None, field: str, *, maximum: int = MAX_SCOPE_COMPONENT_LENGTH) -> str:
        if not isinstance(value, str):
            raise PermissionError(f"{field} must be a string")
        normalized = value.strip()
        if not normalized:
            raise PermissionError(f"{field} is required")
        if len(normalized) > maximum:
            raise ValueError(f"{field} exceeds the maximum length")
        return normalized

    @classmethod
    def _scope(cls, tenant_id: str | None, subject_id: str | None) -> tuple[str, str]:
        return (
            cls._component(tenant_id, "tenant_id"),
            cls._component(subject_id, "subject_id"),
        )

    @classmethod
    def _namespace(cls, namespace: str) -> str:
        return cls._component(namespace, "namespace", maximum=MAX_NAMESPACE_LENGTH)

    @staticmethod
    def _encode_payload(payload: object) -> str:
        try:
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("scoped state payload is not safely serializable") from exc
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("scoped state payload exceeds the maximum size")
        return encoded

    def get(self, *, tenant_id: str | None, subject_id: str | None, namespace: str) -> object | None:
        tenant, subject = self._scope(tenant_id, subject_id)
        namespace = self._namespace(namespace)
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT payload FROM scoped_state WHERE tenant_id=? AND subject_id=? AND namespace=?",
                (tenant, subject, namespace),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError, RecursionError) as exc:
            raise RuntimeError("scoped state is corrupt") from exc

    def put(self, *, tenant_id: str | None, subject_id: str | None, namespace: str, payload: object) -> None:
        tenant, subject = self._scope(tenant_id, subject_id)
        namespace = self._namespace(namespace)
        encoded = self._encode_payload(payload)
        with self._lock, sqlite3.connect(self.database_path) as db:
            db.execute(
                "INSERT INTO scoped_state(tenant_id,subject_id,namespace,payload) VALUES(?,?,?,?) "
                "ON CONFLICT(tenant_id,subject_id,namespace) DO UPDATE SET payload=excluded.payload",
                (tenant, subject, namespace, encoded),
            )
            db.commit()
