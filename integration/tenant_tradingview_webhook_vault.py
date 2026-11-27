"""One-time secret provisioning for tenant-scoped TradingView alert webhooks."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class TenantTradingViewWebhookVault:
    """Resolves webhook secrets to server-owned identity without storing plaintext."""

    def __init__(self, path: str | Path, connections: Any) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connections = connections
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_tradingview_webhook_secrets (
                    secret_hash TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _hash(secret: str) -> str:
        if not isinstance(secret, str) or not 40 <= len(secret) <= 256:
            raise ValueError("segredo TradingView inválido")
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def issue(self, context: TenantContext, connection_id: str) -> str:
        owner = require_tenant_context(context)
        account = next((item for item in self.connections.list_connections(owner)
                        if item["connection_id"] == connection_id), None)
        if account is None or account["provider_id"] != "tradingview_webhook" or account["status"] != "PENDING":
            raise PermissionError("conexão TradingView pendente não encontrada")
        secret = secrets.token_urlsafe(48)
        digest = self._hash(secret)
        with self._connect() as db:
            db.execute("""
                UPDATE tenant_tradingview_webhook_secrets SET revoked=1
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id))
            db.execute("""
                INSERT INTO tenant_tradingview_webhook_secrets
                (secret_hash,tenant_id,subject_id,connection_id)
                VALUES(?,?,?,?)
            """, (digest, owner.tenant_id, owner.subject_id, connection_id))
        return secret

    def resolve_secret(self, secret: str):
        digest = self._hash(secret)
        with self._connect() as db:
            row = db.execute("""
                SELECT tenant_id,subject_id,connection_id
                FROM tenant_tradingview_webhook_secrets
                WHERE secret_hash=? AND revoked=0
            """, (digest,)).fetchone()
        if row is None:
            return None
        return TenantContext(row["tenant_id"], row["subject_id"]), row["connection_id"]

    def verify(self, context: TenantContext, connection_id: str, secret: str) -> bool:
        owner = require_tenant_context(context)
        try:
            digest = self._hash(secret)
        except ValueError:
            return False
        with self._connect() as db:
            row = db.execute("""
                SELECT secret_hash FROM tenant_tradingview_webhook_secrets
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id)).fetchone()
        return bool(row and hmac.compare_digest(row["secret_hash"], digest))

    def revoke(self, context: TenantContext, connection_id: str) -> bool:
        owner = require_tenant_context(context)
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE tenant_tradingview_webhook_secrets SET revoked=1
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked=0
            """, (owner.tenant_id, owner.subject_id, connection_id))
        return cursor.rowcount > 0


class TenantTradingViewWebhookOnboardingService:
    def __init__(self, connections: Any, vault: TenantTradingViewWebhookVault) -> None:
        self.connections = connections
        self.vault = vault

    def provision(self, context: TenantContext, *, account_alias: str) -> dict[str, Any]:
        owner = require_tenant_context(context)
        record = self.connections.record_pending_connection(
            owner, provider_id="tradingview_webhook", account_alias=account_alias,
            account_reference="webhook:" + secrets.token_hex(12),
            capabilities=["alerts:receive"],
        )
        try:
            secret = self.vault.issue(owner, record["connection_id"])
        except Exception:
            self.connections.mark_disconnected(owner, connection_id=record["connection_id"])
            raise
        return {
            **record, "webhook_secret": secret,
            "endpoint_path": f"/api/webhooks/tradingview/{record['connection_id']}",
            "secret_reveal": "ONE_TIME",
            "read_only": True, "execution_authorized": False,
        }
