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

    def list_connections(self, context: TenantContext | None) -> list[dict[str, Any]]:
        trusted = require_tenant_context(context)
        records = self.storage.get(trusted, self.STORAGE_KEY) or []
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RuntimeError("stored broker connection metadata is invalid")
        required = ("connection_id", "provider_id", "account_alias", "status")
        safe = []
        for item in records:
            if any(not isinstance(item.get(field), str) or not item[field] for field in required):
                raise RuntimeError("stored broker connection metadata is malformed")
            capabilities = item.get("capabilities", [])
            if not isinstance(capabilities, list) or any(not isinstance(value, str) for value in capabilities):
                raise RuntimeError("stored broker connection capabilities are malformed")
            safe.append({
                "connection_id": item["connection_id"],
                "provider_id": item["provider_id"],
                "account_alias": item["account_alias"],
                "account_reference": item.get("account_reference"),
                "status": item["status"],
                "last_verified_at": item.get("last_verified_at"),
                "capabilities": list(capabilities),
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
        if (
            not isinstance(account_reference, str)
            or not account_reference.strip()
            or len(account_reference.strip()) > 120
        ):
            raise ValueError("account_reference deve identificar a conta sem conter credenciais")
        clean_capabilities = []
        for capability in capabilities or []:
            if not isinstance(capability, str) or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,63}", capability):
                raise ValueError("capability inválida")
            if capability not in clean_capabilities:
                clean_capabilities.append(capability)
        if len(clean_capabilities) > 30:
            raise ValueError("capabilities excedem o limite")
        if not callable(getattr(self.storage, "upsert_unique_list_item", None)):
            raise RuntimeError("tenant storage does not support atomic broker connection updates")
        record = {
            "connection_id": uuid.uuid4().hex,
            "provider_id": provider_id,
            "account_alias": account_alias.strip(),
            "account_reference": account_reference.strip(),
            "status": "CONNECTED",
            "last_verified_at": self._timestamp(),
            "capabilities": clean_capabilities,
        }
        saved = self.storage.upsert_unique_list_item(
            trusted, self.STORAGE_KEY, record,
            unique_fields=("provider_id", "account_reference"),
            limit=self.MAX_CONNECTIONS,
        )
        return {
            "connection_id": saved["connection_id"],
            "provider_id": saved["provider_id"],
            "account_alias": saved["account_alias"],
            "account_reference": saved["account_reference"],
            "status": saved["status"],
            "last_verified_at": saved.get("last_verified_at"),
            "capabilities": list(saved.get("capabilities", [])),
            "read_only": True,
            "execution_authorized": False,
        }

    def record_pending_connection(
        self, context: TenantContext | None, *, provider_id: str,
        account_alias: str, account_reference: str,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a server-controlled pending relay enrollment; no client can assert CONNECTED."""
        trusted = require_tenant_context(context)
        if not isinstance(provider_id, str) or not self._PROVIDER_ID.fullmatch(provider_id):
            raise ValueError("provider_id inválido")
        if not isinstance(account_alias, str) or not account_alias.strip() or len(account_alias.strip()) > 80:
            raise ValueError("account_alias inválido")
        if not isinstance(account_reference, str) or not account_reference.strip() or len(account_reference.strip()) > 120:
            raise ValueError("account_reference inválida")
        clean = []
        for value in capabilities or []:
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,63}", value):
                raise ValueError("capability inválida")
            if value not in clean:
                clean.append(value)
        if not callable(getattr(self.storage, "upsert_unique_list_item", None)):
            raise RuntimeError("tenant storage does not support atomic broker connection updates")
        record = {
            "connection_id": uuid.uuid4().hex, "provider_id": provider_id,
            "account_alias": account_alias.strip(), "account_reference": account_reference.strip(),
            "status": "PENDING", "last_verified_at": None, "capabilities": clean,
        }
        saved = self.storage.upsert_unique_list_item(
            trusted, self.STORAGE_KEY, record,
            unique_fields=("provider_id", "account_reference"), limit=self.MAX_CONNECTIONS,
        )
        return {
            "connection_id": saved["connection_id"], "provider_id": saved["provider_id"],
            "account_alias": saved["account_alias"], "account_reference": saved["account_reference"],
            "status": saved["status"], "capabilities": list(saved.get("capabilities", [])),
            "read_only": True, "execution_authorized": False,
        }

    def mark_connected_after_provider_handshake(
        self, context: TenantContext | None, *, connection_id: str,
        account_reference: str, capabilities: list[str],
    ) -> bool:
        """Promote an owned pending account only after its provider handshake."""
        trusted = require_tenant_context(context)
        if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
            raise ValueError("connection_id inválido")
        if not isinstance(account_reference, str) or not account_reference.strip() or len(account_reference.strip()) > 120:
            raise ValueError("account_reference inválida")
        clean: list[str] = []
        for value in capabilities:
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,63}", value):
                raise ValueError("capability inválida")
            if value not in clean:
                clean.append(value)
        records = self.list_connections(trusted)
        target = next((item for item in records if item["connection_id"] == connection_id), None)
        if target is None or target["status"] != "PENDING":
            raise PermissionError("somente uma conexão pendente e pertencente à identidade pode ser ativada")
        updates = {
            "provider_id": target["provider_id"],
            "status": "CONNECTED",
            "account_reference": account_reference.strip(),
            "capabilities": clean,
            "last_verified_at": self._timestamp(),
        }
        unique_update = getattr(self.storage, "update_list_item_unique", None)
        if callable(unique_update):
            try:
                return unique_update(
                    trusted, self.STORAGE_KEY, match_field="connection_id",
                    match_value=connection_id, updates=updates,
                    unique_fields=("provider_id", "account_reference"),
                )
            except ValueError as exc:
                if "unique tenant list identity already exists" in str(exc):
                    raise ValueError("esta conta do provedor já está vinculada a outra conexão") from exc
                raise
        if any(
            item["connection_id"] != connection_id
            and item["provider_id"] == target["provider_id"]
            and item.get("account_reference") == account_reference.strip()
            for item in records
        ):
            raise ValueError("esta conta do provedor já está vinculada a outra conexão")
        if not callable(getattr(self.storage, "update_list_item", None)):
            raise RuntimeError("tenant storage does not support atomic broker connection updates")
        return self.storage.update_list_item(
            trusted, self.STORAGE_KEY, match_field="connection_id",
            match_value=connection_id, updates=updates,
        )

    def mark_connected_after_relay_handshake(
        self, context: TenantContext | None, *, connection_id: str,
    ) -> bool:
        trusted = require_tenant_context(context)
        if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
            raise ValueError("connection_id inválido")
        if not callable(getattr(self.storage, "update_list_item", None)):
            raise RuntimeError("tenant storage does not support atomic broker connection updates")
        return self.storage.update_list_item(
            trusted, self.STORAGE_KEY, match_field="connection_id",
            match_value=connection_id,
            updates={"status": "CONNECTED", "last_verified_at": self._timestamp()},
        )

    def mark_disconnected(
        self, context: TenantContext | None, *, connection_id: str
    ) -> bool:
        trusted = require_tenant_context(context)
        if not isinstance(connection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", connection_id):
            raise ValueError("connection_id inválido")
        if not callable(getattr(self.storage, "update_list_item", None)):
            raise RuntimeError("tenant storage does not support atomic broker connection updates")
        return self.storage.update_list_item(
            trusted, self.STORAGE_KEY, match_field="connection_id",
            match_value=connection_id, updates={"status": "DISCONNECTED"},
        )
