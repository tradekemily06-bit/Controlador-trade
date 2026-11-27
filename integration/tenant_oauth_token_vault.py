"""Tenant-scoped encrypted OAuth token storage.

Encryption is deliberately delegated to a host KMS/envelope-encryption provider.
This module never implements home-grown cryptography and fails closed when no
production cipher is injected.
"""
from __future__ import annotations
import base64
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context

_CONNECTION_ID = re.compile(r"^[a-f0-9]{32}$")
_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

class TenantOAuthTokenVault:
    """Encrypted token persistence with tenant/connection-bound AAD."""

    def __init__(self, path: str | Path, connections: Any, cipher: Any) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        if cipher is None or not callable(getattr(cipher, "encrypt", None)) or not callable(getattr(cipher, "decrypt", None)):
            raise ValueError("production KMS cipher with encrypt/decrypt is required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connections = connections
        self.cipher = cipher
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_oauth_tokens (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    ciphertext_b64 TEXT NOT NULL,
                    expires_at TEXT,
                    scopes_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    revoked_at TEXT,
                    PRIMARY KEY (tenant_id, subject_id, connection_id)
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def _owned_connection(self, owner: TenantContext, connection_id: str, provider_id: str | None = None):
        if not isinstance(connection_id, str) or not _CONNECTION_ID.fullmatch(connection_id):
            raise ValueError("connection_id inválido")
        account = next((item for item in self.connections.list_connections(owner)
                        if item["connection_id"] == connection_id), None)
        if account is None:
            raise PermissionError("conexão não pertence a esta identidade")
        if provider_id is not None and account["provider_id"] != provider_id:
            raise PermissionError("provedor não corresponde à conexão")
        if account["status"] not in {"PENDING", "CONNECTED"}:
            raise PermissionError("conexão não está habilitada para credenciais OAuth")
        return account

    @staticmethod
    def _aad(owner: TenantContext, connection_id: str, provider_id: str) -> bytes:
        return json.dumps({
            "tenant_id": owner.tenant_id,
            "subject_id": owner.subject_id,
            "connection_id": connection_id,
            "provider_id": provider_id,
            "purpose": "broker-oauth-token-v1",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _validate_tokens(token_set: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(token_set, Mapping):
            raise ValueError("token_set deve ser um objeto")
        access = token_set.get("access_token")
        refresh = token_set.get("refresh_token")
        token_type = token_set.get("token_type", "Bearer")
        if not isinstance(access, str) or not access or len(access) > 16384:
            raise ValueError("access_token inválido")
        if refresh is not None and (not isinstance(refresh, str) or not refresh or len(refresh) > 16384):
            raise ValueError("refresh_token inválido")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ValueError("token_type não suportado")
        normalized = {"access_token": access, "token_type": "Bearer"}
        if refresh is not None:
            normalized["refresh_token"] = refresh
        return normalized

    def store(self, context: TenantContext, *, connection_id: str, provider_id: str,
              token_set: Mapping[str, Any], expires_at: str | None = None,
              scopes: tuple[str, ...] = ()) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if not isinstance(provider_id, str) or not _PROVIDER_ID.fullmatch(provider_id):
            raise ValueError("provider_id inválido")
        account = self._owned_connection(owner, connection_id, provider_id)
        tokens = self._validate_tokens(token_set)
        if expires_at is not None:
            if not isinstance(expires_at, str):
                raise ValueError("expires_at inválido")
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("expires_at deve conter fuso horário")
            expires_at = parsed.astimezone(timezone.utc).isoformat()
        clean_scopes = []
        if not isinstance(scopes, (tuple, list)) or len(scopes) > 50:
            raise ValueError("scopes inválidos")
        for scope in scopes:
            if not isinstance(scope, str) or not scope.strip() or len(scope) > 128:
                raise ValueError("scope inválido")
            if scope not in clean_scopes:
                clean_scopes.append(scope)
        aad = self._aad(owner, connection_id, provider_id)
        encrypted = self.cipher.encrypt(
            json.dumps(tokens, separators=(",", ":"), sort_keys=True).encode("utf-8"),
            associated_data=aad,
        )
        if not isinstance(encrypted, Mapping):
            raise RuntimeError("KMS cipher returned an invalid envelope")
        key_id, ciphertext = encrypted.get("key_id"), encrypted.get("ciphertext")
        if not isinstance(key_id, str) or not key_id or len(key_id) > 256:
            raise RuntimeError("KMS key identifier missing")
        if not isinstance(ciphertext, bytes) or not ciphertext:
            raise RuntimeError("KMS ciphertext missing")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                INSERT INTO tenant_oauth_tokens
                (tenant_id,subject_id,connection_id,provider_id,key_id,ciphertext_b64,
                 expires_at,scopes_json,updated_at,revoked_at)
                VALUES(?,?,?,?,?,?,?,?,?,NULL)
                ON CONFLICT(tenant_id,subject_id,connection_id) DO UPDATE SET
                  provider_id=excluded.provider_id,key_id=excluded.key_id,
                  ciphertext_b64=excluded.ciphertext_b64,expires_at=excluded.expires_at,
                  scopes_json=excluded.scopes_json,updated_at=excluded.updated_at,revoked_at=NULL
            """, (owner.tenant_id, owner.subject_id, connection_id, provider_id,
                  key_id, base64.b64encode(ciphertext).decode("ascii"),
                  expires_at, json.dumps(clean_scopes), now))
            db.execute("COMMIT")
        return {
            "connection_id": connection_id,
            "provider_id": provider_id,
            "status": "STORED_ENCRYPTED",
            "expires_at": expires_at,
            "scopes": clean_scopes,
            "updated_at": now,
            "secret_material_returned": False,
            "execution_authorized": False,
        }

    def resolve(self, context: TenantContext, connection_id: str) -> dict[str, Any] | None:
        """Resolve credentials for trusted server-side adapter code only."""
        owner = require_tenant_context(context)
        account = self._owned_connection(owner, connection_id)
        with self._connect() as db:
            row = db.execute("""
                SELECT provider_id,key_id,ciphertext_b64,expires_at,scopes_json,revoked_at
                FROM tenant_oauth_tokens
                WHERE tenant_id=? AND subject_id=? AND connection_id=?
            """, (owner.tenant_id, owner.subject_id, connection_id)).fetchone()
        if row is None or row[5] is not None or row[0] != account["provider_id"]:
            return None
        if row[3] is not None:
            expires = datetime.fromisoformat(row[3])
            if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
                return None
        try:
            ciphertext = base64.b64decode(row[2], validate=True)
            plaintext = self.cipher.decrypt(
                ciphertext, key_id=row[1],
                associated_data=self._aad(owner, connection_id, row[0]),
            )
            tokens = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("OAuth token envelope could not be authenticated/decrypted") from exc
        if not isinstance(tokens, dict):
            raise RuntimeError("decrypted OAuth token payload is malformed")
        return {
            **tokens,
            "provider_id": row[0],
            "connection_id": connection_id,
            "scopes": json.loads(row[4]),
            "expires_at": row[3],
        }

    def revoke(self, context: TenantContext, connection_id: str) -> bool:
        owner = require_tenant_context(context)
        self._owned_connection(owner, connection_id)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            cursor = db.execute("""
                UPDATE tenant_oauth_tokens SET revoked_at=?,ciphertext_b64='',updated_at=?
                WHERE tenant_id=? AND subject_id=? AND connection_id=? AND revoked_at IS NULL
            """, (now, now, owner.tenant_id, owner.subject_id, connection_id))
            return cursor.rowcount == 1
