from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock


class SQLiteScopedStateStore:
    """Small durable JSON state store keyed by tenant, subject and namespace.

    This is a single-instance provider. It is deliberately not presented as a
    distributed SaaS database; multi-instance deployments must use a shared
    provider before production is enabled.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self.database_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scoped_state ("
                "tenant_id TEXT NOT NULL, subject_id TEXT NOT NULL, "
                "namespace TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY (tenant_id, subject_id, namespace))"
            )
            db.commit()

    @staticmethod
    def _scope(tenant_id: str | None, subject_id: str | None) -> tuple[str, str]:
        tenant = str(tenant_id or "").strip()
        subject = str(subject_id or "").strip()
        if not tenant or not subject:
            raise PermissionError("tenant_id and subject_id are required")
        return tenant, subject

    def get(self, *, tenant_id: str | None, subject_id: str | None, namespace: str) -> object | None:
        tenant, subject = self._scope(tenant_id, subject_id)
        namespace = str(namespace).strip()
        if not namespace:
            raise ValueError("namespace is required")
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT payload FROM scoped_state WHERE tenant_id=? AND subject_id=? AND namespace=?",
                (tenant, subject, namespace),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("scoped state is corrupt") from exc

    def put(self, *, tenant_id: str | None, subject_id: str | None, namespace: str, payload: object) -> None:
        tenant, subject = self._scope(tenant_id, subject_id)
        namespace = str(namespace).strip()
        if not namespace:
            raise ValueError("namespace is required")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock, sqlite3.connect(self.database_path) as db:
            db.execute(
                "INSERT INTO scoped_state(tenant_id,subject_id,namespace,payload) VALUES(?,?,?,?) "
                "ON CONFLICT(tenant_id,subject_id,namespace) DO UPDATE SET payload=excluded.payload",
                (tenant, subject, namespace, encoded),
            )
            db.commit()
