from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_NONCE_BYTES = 12


class PostgresEncryptedPushSubscriptionStore:
    """Shared PostgreSQL store with application-layer AES-256-GCM encryption.

    The connection factory must be an explicitly attested shared PostgreSQL
    provider (shared_database=True and production_durable=True). This prevents
    a local SQLite connection from accidentally satisfying the production
    storage contract. The encryption key is resolved for each operation and
    is never retained by this object.
    """

    production_durable = True
    encrypted_at_rest = True

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        encryption_key_provider: Callable[[str], bytes],
        *,
        key_version: str,
    ) -> None:
        if not callable(connection_factory):
            raise ValueError("connection_factory must be callable")
        if getattr(connection_factory, "shared_database", False) is not True:
            raise RuntimeError("a shared PostgreSQL connection factory is required")
        if getattr(connection_factory, "production_durable", False) is not True:
            raise RuntimeError("the PostgreSQL provider must attest production durability")
        if not callable(encryption_key_provider):
            raise ValueError("encryption_key_provider must be callable")
        if not isinstance(key_version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_version):
            raise ValueError("key_version must be a non-empty opaque version")
        self._connection_factory = connection_factory
        self._encryption_key_provider = encryption_key_provider
        self.key_version = key_version
        # Validate the secret at composition but do not retain key material.
        self._key()

    def _key(self) -> bytes:
        key = self._encryption_key_provider(self.key_version)
        if not isinstance(key, bytes) or len(key) != 32:
            raise RuntimeError("push subscription encryption key must contain exactly 32 bytes")
        return key

    @staticmethod
    def _owner(context: TenantContext | None) -> tuple[str, str]:
        owner = require_tenant_context(context)
        if not isinstance(owner, TenantContext):
            raise PermissionError("trusted tenant context is required")
        return owner.tenant_id, owner.subject_id

    @staticmethod
    def _aad(tenant_id: str, subject_id: str, device_id: str, key_version: str) -> bytes:
        return json.dumps(
            [tenant_id, subject_id, device_id, key_version],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def initialize_schema(self) -> None:
        """Create the table/index; run through the deployment migration identity."""
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS controlador_push_subscriptions (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    key_version TEXT NOT NULL,
                    nonce BYTEA NOT NULL,
                    encrypted_payload BYTEA NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, subject_id, device_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_controlador_push_owner
                ON controlador_push_subscriptions (tenant_id, subject_id)
                """
            )
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def put_for_owner(
        self, context: TenantContext, device_id: str, record: dict[str, Any]
    ) -> None:
        tenant_id, subject_id = self._owner(context)
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id is invalid")
        if not isinstance(record, dict):
            raise ValueError("subscription record must be an object")
        encoded = json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = AESGCM(self._key()).encrypt(
            nonce, encoded, self._aad(tenant_id, subject_id, device_id, self.key_version)
        )
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO controlador_push_subscriptions
                    (tenant_id, subject_id, device_id, key_version, nonce, encrypted_payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, subject_id, device_id) DO UPDATE SET
                    key_version = EXCLUDED.key_version,
                    nonce = EXCLUDED.nonce,
                    encrypted_payload = EXCLUDED.encrypted_payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (tenant_id, subject_id, device_id, self.key_version, nonce, encrypted),
            )
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def list_for_owner(self, context: TenantContext) -> list[dict[str, Any]]:
        tenant_id, subject_id = self._owner(context)
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT device_id, key_version, nonce, encrypted_payload
                FROM controlador_push_subscriptions
                WHERE tenant_id = %s AND subject_id = %s
                ORDER BY device_id
                """,
                (tenant_id, subject_id),
            )
            rows = cursor.fetchall()
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

        records: list[dict[str, Any]] = []
        for row in rows:
            device_id, key_version, nonce, encrypted = row
            if not isinstance(device_id, str) or not isinstance(key_version, str):
                raise RuntimeError("stored push subscription metadata is invalid")
            try:
                plaintext = AESGCM(self._key_for_version(key_version)).decrypt(
                    bytes(nonce),
                    bytes(encrypted),
                    self._aad(tenant_id, subject_id, device_id, key_version),
                )
                record = json.loads(plaintext.decode("utf-8"))
            except Exception as exc:
                raise RuntimeError("push subscription record could not be authenticated") from exc
            if not isinstance(record, dict):
                raise RuntimeError("stored push subscription payload is invalid")
            records.append({**record, "device_id": device_id})
        return records

    def _key_for_version(self, key_version: str) -> bytes:
        if not isinstance(key_version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_version):
            raise RuntimeError("stored push subscription key version is invalid")
        key = self._encryption_key_provider(key_version)
        if not isinstance(key, bytes) or len(key) != 32:
            raise RuntimeError("push subscription encryption key is unavailable")
        return key

    def delete_for_owner(self, context: TenantContext, device_id: str) -> bool:
        tenant_id, subject_id = self._owner(context)
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id is invalid")
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                DELETE FROM controlador_push_subscriptions
                WHERE tenant_id = %s AND subject_id = %s AND device_id = %s
                """,
                (tenant_id, subject_id, device_id),
            )
            deleted = cursor.rowcount == 1
            connection.commit()
            return deleted
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
