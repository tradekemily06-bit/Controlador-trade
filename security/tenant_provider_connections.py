"""Tenant-scoped, secret-free metadata for verified broker connections.

This registry is deliberately not an OAuth/credential vault. A connection can
be marked CONNECTED only by an internal adapter after a real handshake; browser
input cannot assert that a broker account is connected.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import TenantStorageBoundary, require_tenant_context


class TenantProviderConnectionRegistry:
    STORAGE_KEY = "broker_provider_connections_v1"
    MAX_CONNECTIONS = 50
    _PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

    def __init__(self, storage: TenantStorageBoundary) -> None:
        if storage is None or not callable(getattr(storage, "get", None)) or not callable(getattr(storage, "put", None)):
            raise ValueError("tenant-scoped storage is required")
        self.storage = storage

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _read_records(cls, context: TenantContext) -> list[dict[str, Any]]:
        return []

    def list_connections(self, context: TenantContext | None) -> list[dict[str, Any]]:
        trusted = require_tenant_context(context)
        records = self.storage.get(trusted, self.STORAGE_KEY) or []
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RuntimeError("stored broker connection metadata is invalid")
        # Only explicitly allowlisted, non-secret fields leave this boundary.
        safe = []
        for item in records:
            safe.append({
                "connection_id": item["connection_id"],
                "provider_id": item["provider_id"],
                "account_alias": item["account_alias"],
                "account_reference": item.get("account_reference"),
                "status": item["status"],
                "last_verified_at": item.get("last_verified_at"),
                "capabilities": list(item.get("capabilities", [])),
                "read_only": True,
                "execution_authorized": False,
            })
        return safe

    def record_verified_connection(
        self,
        context: TenantContext | None,
        *,
        provider_id: str,
        account_alias: str,
        account_reference: str | None = None,
        capabilities: list[str] | None = None,
        adapter_verified: bool,
    ) -> dict[str, Any]:
        """Persist a connection only after a trusted adapter confirms handshake."""
        trusted = require_tenant_context(context)
        if adapter_verified is not True:
            raise PermissionError("broker connection requires a verified adapter handshake")
        if not isinstance(provider_id, str) or not self._PROVIDER_ID.fullmatch(provider_id):
            raise ValueError("provider_id inválido")
        if not isinstance(account_alias, str) or not account_alias.strip() or len(account_alias.strip()) > 80:
            raise ValueError("account_alias deve conter de 1 a 80 caracteres")
        if account_reference is not None and (
            not isinstance(account_reference, str) or len(account_reference.strip()) > 120
        ):
            raise ValueError("account_reference inválido")
        clean_capabilities = []
        for capability in capabilities or []:
            if not isinstance(capability, str) or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,63}", capability):
                raise ValueError("capability inválida")
            if capability not in clean_capabilities:
                clean_capabilities.append(capability)
        if len(clean_capabilities) > 30:
            raise ValueError("capabilities excedem o limite")
        records = self.storage.get(trusted, self.STORAGE_KEY) or []
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RuntimeError("stored broker connection metadata is invalid")
        # A broker account is unique within one user's tenant scope.
        for item in records:
            if item.get("provider_id") == provider_id and item.get("account_reference") == account_reference:
                item.update({
                    "account_alias": account_alias.strip(),
                    "status": "CONNECTED",
                    "last_verified_at": self._timestamp(),
                    "capabilities": clean_capabilities,
                })
                self.storage.put(trusted, self.STORAGE_KEY, records)
                return self.list_connections(trusted)[records.index(item)]
        if len(records) >= self.MAX_CONNECTIONS:
            raise ValueError("limite de conexões de corretoras atingido")
        record = {
            "connection_id": uuid.uuid4().hex,
            "provider_id": provider_id,
            "account_alias": account_alias.strip(),
            "account_reference": account_reference.strip() if account_reference else None,
            "status": "CONNECTED",
            "last_verified_at": self._timestamp(),
            "capabilities": clean_capabilities,
        }
        records.append(record)
        self.storage.put(trusted, self.STORAGE_KEY, records)
        return self.list_connections(trusted)[-1]

    def mark_disconnected(
        self, context: TenantContext | None, *, connection_id: str
    ) -> bool:
        trusted = require_tenant_context(context)
        if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
            raise ValueError("connection_id inválido")
        records = self.storage.get(trusted, self.STORAGE_KEY) or []
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RuntimeError("stored broker connection metadata is invalid")
        for item in records:
            if item.get("connection_id") == connection_id:
                item["status"] = "DISCONNECTED"
                self.storage.put(trusted, self.STORAGE_KEY, records)
                return True
        return False
