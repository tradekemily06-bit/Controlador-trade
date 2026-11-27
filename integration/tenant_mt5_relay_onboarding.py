"""Provisioning and hashed-token authentication for isolated MT5 DEMO relays."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class TenantMT5RelayTokenVault:
    """Stores only SHA-256 hashes of high-entropy relay tokens and trusted scope."""

    def __init__(self, path: str | Path, connections: Any) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connections = connections
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_mt5_relay_tokens (
                    token_hash TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mt5_relay_scope ON tenant_mt5_relay_tokens(tenant_id, subject_id, connection_id)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _hash(token: str) -> str:
        if not isinstance(token, str) or not 40 <= len(token) <= 256:
            raise ValueError("token MT5 inválido")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(self, context: TenantContext, connection_id: str) -> dict[str, str]:
        owner = require_tenant_context(context)
        account = next((item for item in self.connections.list_connections(owner)
                        if item["connection_id"] == connection_id), None)
        if account is None or account["provider_id"] != "mt5_relay" or account["status"] != "PENDING":
            raise PermissionError("conexão MT5 pendente não encontrada")
        token = secrets.token_urlsafe(48)
        source_id = "mt5_" + secrets.token_hex(16)
        digest = self._hash(token)
        with self._connect() as db:
            db.execute("""
                UPDATE tenant_mt5_relay_tokens SET revoked=1
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id))
            db.execute("""
                INSERT INTO tenant_mt5_relay_tokens
                (token_hash,tenant_id,subject_id,connection_id,source_id)
                VALUES(?,?,?,?,?)
            """, (digest, owner.tenant_id, owner.subject_id, connection_id, source_id))
        return {"relay_token": token, "source_id": source_id}

    def resolve(self, token: str):
        digest = self._hash(token)
        with self._connect() as db:
            row = db.execute("""
                SELECT tenant_id,subject_id,connection_id FROM tenant_mt5_relay_tokens
                WHERE token_hash=? AND revoked=0
            """, (digest,)).fetchone()
        if row is None:
            return None
        return TenantContext(row["tenant_id"], row["subject_id"]), row["connection_id"]

    def source_id(self, context: TenantContext, connection_id: str) -> str:
        owner = require_tenant_context(context)
        with self._connect() as db:
            row = db.execute("""
                SELECT source_id FROM tenant_mt5_relay_tokens
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id)).fetchone()
        if row is None:
            raise PermissionError("origem MT5 não provisionada para esta conexão")
        return row["source_id"]

    def revoke(self, context: TenantContext, connection_id: str) -> bool:
        owner = require_tenant_context(context)
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE tenant_mt5_relay_tokens SET revoked=1
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id))
        return cursor.rowcount > 0


class TenantMT5RelayOnboardingService:
    """Creates a pending DEMO relay account and reveals its one-time token once."""

    def __init__(self, connections: Any, token_vault: TenantMT5RelayTokenVault) -> None:
        self.connections = connections
        self.token_vault = token_vault

    def provision(self, context: TenantContext, *, account_alias: str) -> dict[str, Any]:
        owner = require_tenant_context(context)
        record = self.connections.record_pending_connection(
            owner, provider_id="mt5_relay", account_alias=account_alias,
            account_reference="relay:" + secrets.token_hex(12),
            capabilities=["candles:read", "account-mode:demo"],
        )
        try:
            credentials = self.token_vault.issue(owner, record["connection_id"])
        except Exception:
            self.connections.mark_disconnected(owner, connection_id=record["connection_id"])
            raise
        return {
            **record, **credentials,
            "endpoint_path": f"/api/bridge/mt5/connections/{record['connection_id']}/candles",
            "token_reveal": "ONE_TIME",
            "read_only": True, "execution_authorized": False,
        }
