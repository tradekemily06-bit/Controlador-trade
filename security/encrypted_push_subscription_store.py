from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Callable, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_NAMESPACE = "push-subscription:v1:"
_NONCE_BYTES = 12


class DurableTenantRecordBackend(Protocol):
    """Host storage contract; list_keys must be scoped by the supplied owner."""

    production_durable: bool

    def get(self, context: TenantContext, key: str) -> Any | None: ...
    def put(self, context: TenantContext, key: str, value: Any) -> None: ...
    def delete(self, context: TenantContext, key: str) -> None: ...
    def list_keys(self, context: TenantContext, prefix: str) -> list[str]: ...


class EncryptedTenantPushSubscriptionStore:
    """AES-GCM envelope encryption over a durable, tenant-scoped record backend.

    The backend stores only versioned ciphertext envelopes. The 256-bit
    encryption key is fetched from host secret management for each operation.
    This adapter is production-durable only when its backend explicitly
    declares that property; local SQLite must not be promoted by configuration.
    """

    production_durable = True
    encrypted_at_rest = True

    def __init__(
        self,
        backend: DurableTenantRecordBackend,
        encryption_key_provider: Callable[[], bytes],
    ) -> None:
        if backend is None or getattr(backend, "production_durable", False) is not True:
            raise RuntimeError("a production-durable tenant record backend is required")
        for method in ("get", "put", "delete", "list_keys"):
            if not callable(getattr(backend, method, None)):
                raise ValueError(f"backend must implement {method}")
        if not callable(encryption_key_provider):
            raise ValueError("encryption_key_provider must be callable")
        self.backend = backend
        self._encryption_key_provider = encryption_key_provider

    def _cipher(self) -> AESGCM:
        key = self._encryption_key_provider()
        if not isinstance(key, bytes) or len(key) != 32:
            raise RuntimeError("push subscription encryption key must be 32 secret-managed bytes")
        return AESGCM(key)

    @staticmethod
    def _record_key(device_id: str) -> str:
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id is invalid")
        return _NAMESPACE + device_id

    @staticmethod
    def _aad(context: TenantContext, device_id: str) -> bytes:
        return json.dumps(
            [context.tenant_id, context.subject_id, device_id, 1],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def _encrypt(self, context: TenantContext, device_id: str, record: dict[str, Any]) -> dict[str, str]:
        nonce = os.urandom(_NONCE_BYTES)
        plaintext = json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        ciphertext = self._cipher().encrypt(nonce, plaintext, self._aad(context, device_id))
        return {
            "version": "1",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        }

    def _decrypt(self, context: TenantContext, device_id: str, envelope: Any) -> dict[str, Any]:
        if not isinstance(envelope, dict) or envelope.get("version") != "1":
            raise RuntimeError("stored push subscription envelope is invalid")
        try:
            nonce = base64.urlsafe_b64decode(envelope["nonce"])
            ciphertext = base64.urlsafe_b64decode(envelope["ciphertext"])
            if len(nonce) != _NONCE_BYTES:
                raise ValueError("invalid nonce")
            plaintext = self._cipher().decrypt(
                nonce, ciphertext, self._aad(context, device_id)
            )
            record = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            # Do not expose ciphertext, key material, or provider details.
            raise RuntimeError("stored push subscription could not be authenticated") from exc
        if not isinstance(record, dict):
            raise RuntimeError("stored push subscription record has an invalid shape")
        return record

    def list_for_owner(self, context: TenantContext) -> list[dict[str, Any]]:
        owner = require_tenant_context(context)
        keys = self.backend.list_keys(owner, _NAMESPACE)
        if not isinstance(keys, list):
            raise RuntimeError("tenant backend returned an invalid key listing")
        records: list[dict[str, Any]] = []
        for key in keys:
            if not isinstance(key, str) or not key.startswith(_NAMESPACE):
                raise RuntimeError("tenant backend returned a key outside the push namespace")
            device_id = key[len(_NAMESPACE):]
            self._record_key(device_id)
            envelope = self.backend.get(owner, key)
            # A concurrent revoke may remove a key after list_keys returns it.
            if envelope is None:
                continue
            record = self._decrypt(owner, device_id, envelope)
            record["device_id"] = device_id
            records.append(record)
        return records

    def put_for_owner(
        self, context: TenantContext, device_id: str, record: dict[str, Any]
    ) -> None:
        owner = require_tenant_context(context)
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        key = self._record_key(device_id)
        self.backend.put(owner, key, self._encrypt(owner, device_id, record))

    def delete_for_owner(self, context: TenantContext, device_id: str) -> bool:
        owner = require_tenant_context(context)
        key = self._record_key(device_id)
        existed = self.backend.get(owner, key) is not None
        if existed:
            self.backend.delete(owner, key)
        return existed
