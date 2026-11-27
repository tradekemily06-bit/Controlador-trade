"""One-time, tenant-bound OAuth state for broker authorization callbacks.

The raw state is returned once to the browser/provider redirect. Only its
SHA-256 digest and trusted owner/connection scope are persisted.
"""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context

class TenantOAuthStateVault:
    """CSRF/replay protection for provider OAuth redirects."""
    def __init__(self, path: str | Path, connections: Any, *,
                 allowed_providers: tuple[str, ...] = ("ctrader_open_api",),
                 ttl_seconds: int = 600) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        if not isinstance(allowed_providers, tuple) or not allowed_providers:
            raise ValueError("allowed_providers must be a non-empty tuple")
        if any(not isinstance(item, str) or not item for item in allowed_providers):
            raise ValueError("allowed provider identifiers are invalid")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 1800:
            raise ValueError("OAuth state TTL must be between 60 and 1800 seconds")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connections = connections
        self.allowed_providers = frozenset(allowed_providers)
        self.ttl_seconds = ttl_seconds
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_oauth_states (
                    state_hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL, connection_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL, expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tenant_oauth_state_scope
                ON tenant_oauth_states(tenant_id, subject_id, connection_id)
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    @staticmethod
    def _digest(state: str) -> str:
        if not isinstance(state, str) or not 40 <= len(state) <= 256:
            raise ValueError("OAuth state inválido")
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def issue(self, context: TenantContext, *, connection_id: str,
              provider_id: str) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if provider_id not in self.allowed_providers:
            raise ValueError("OAuth provider não habilitado")
        account = next((item for item in self.connections.list_connections(owner)
                        if item["connection_id"] == connection_id), None)
        if account is None or account["provider_id"] != provider_id or account["status"] != "PENDING":
            raise PermissionError("conexão OAuth pendente não pertence a esta identidade")
        state = secrets.token_urlsafe(48)
        digest = self._digest(state)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self.ttl_seconds)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM tenant_oauth_states WHERE expires_at < ? OR consumed_at IS NOT NULL",
                       (now.isoformat(),))
            db.execute("""
                INSERT INTO tenant_oauth_states
                (state_hash,tenant_id,subject_id,connection_id,provider_id,expires_at)
                VALUES(?,?,?,?,?,?)
            """, (digest, owner.tenant_id, owner.subject_id, connection_id,
                  provider_id, expires.isoformat()))
            db.execute("COMMIT")
        return {"state": state, "expires_at": expires.isoformat(), "state_reveal": "ONE_TIME"}

    def consume(self, state: str) -> tuple[TenantContext, str, str] | None:
        try:
            digest = self._digest(state)
        except ValueError:
            return None
        now = datetime.now(timezone.utc)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""
                SELECT tenant_id,subject_id,connection_id,provider_id,expires_at,consumed_at
                FROM tenant_oauth_states WHERE state_hash=?
            """, (digest,)).fetchone()
            if row is None or row[5] is not None:
                db.execute("ROLLBACK")
                return None
            try:
                expires = datetime.fromisoformat(row[4])
            except (TypeError, ValueError):
                db.execute("DELETE FROM tenant_oauth_states WHERE state_hash=?", (digest,))
                db.execute("COMMIT")
                return None
            if expires.tzinfo is None or expires <= now:
                db.execute("DELETE FROM tenant_oauth_states WHERE state_hash=?", (digest,))
                db.execute("COMMIT")
                return None
            db.execute("UPDATE tenant_oauth_states SET consumed_at=? WHERE state_hash=? AND consumed_at IS NULL",
                       (now.isoformat(), digest))
            db.execute("COMMIT")
        return TenantContext(row[0], row[1]), row[2], row[3]
