from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import TenantStorageBoundary, require_tenant_context


class SQLiteTenantStorage(TenantStorageBoundary):
    """SQLite key/value storage with mandatory tenant scoping.

    This implementation provides durable local persistence and logical
    tenant separation inside one database. It is deliberately NOT marked
    production_durable: SQLite on one runtime does not provide the
    multi-instance, backup, identity-provider, or operational guarantees
    required for production SaaS.
    """

    production_durable = False
    _MAX_KEY_LENGTH = 200

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tenant_state (
                    tenant_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, key)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tenant_state_updated "
                "ON tenant_state(tenant_id, updated_at)"
            )

    @classmethod
    def _scope(cls, context: TenantContext | None, key: str) -> tuple[str, str]:
        trusted = require_tenant_context(context)
        if not isinstance(trusted, TenantContext):
            raise PermissionError("valid trusted tenant context is required")
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        normalized_key = key.strip()
        if not normalized_key or len(normalized_key) > cls._MAX_KEY_LENGTH:
            raise ValueError("key must contain 1 to 200 characters")
        return trusted.tenant_id, normalized_key

    def get(self, context: TenantContext, key: str) -> Any | None:
        tenant_id, normalized_key = self._scope(context, key)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND key=?",
                (tenant_id, normalized_key),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def put(self, context: TenantContext, key: str, value: Any) -> None:
        tenant_id, normalized_key = self._scope(context, key)
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tenant_state(tenant_id, key, value_json)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (tenant_id, normalized_key, encoded),
            )

    def delete(self, context: TenantContext, key: str) -> None:
        tenant_id, normalized_key = self._scope(context, key)
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM tenant_state WHERE tenant_id=? AND key=?",
                (tenant_id, normalized_key),
            )
