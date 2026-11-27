"""Tenant/account-isolated MT5 relay stores.

The HTTP authentication layer must resolve the relay token to a trusted
TenantContext before calling this service. Client payloads never select a
tenant, account, database path, or expected source id.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from data.feed import MarketDataRequest
from integration.mt5_relay_store import MT5RelayStore
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class TenantMT5RelayRegistry:
    """Resolve one durable DEMO relay store per verified tenant connection."""

    def __init__(
        self,
        connections: Any,
        runtime_dir: str | Path,
        source_id_resolver: Callable[[TenantContext, str], str],
    ) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        if not callable(source_id_resolver):
            raise ValueError("trusted source_id_resolver is required")
        self.connections = connections
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.source_id_resolver = source_id_resolver
        self._stores: dict[tuple[str, str, str], MT5RelayStore] = {}

    @staticmethod
    def _connection_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("connection_id inválido")
        return value

    def _resolve(self, context: TenantContext, connection_id: str) -> tuple[tuple[str, str, str], MT5RelayStore]:
        owner = require_tenant_context(context)
        connection = self._connection_id(connection_id)
        account = next(
            (item for item in self.connections.list_connections(owner)
             if item["connection_id"] == connection),
            None,
        )
        if account is None:
            raise PermissionError("conexão MT5 não pertence a esta identidade")
        if account.get("provider_id") != "mt5_relay":
            raise PermissionError("conexão não é do provider mt5_relay")
        if account.get("status") != "CONNECTED":
            raise PermissionError("conexão MT5 precisa de handshake vigente")
        source_id = self.source_id_resolver(owner, connection)
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", source_id):
            raise PermissionError("origem MT5 não provisionada pelo servidor")
        key = (owner.tenant_id, owner.subject_id, connection)
        store = self._stores.get(key)
        if store is None:
            # Hash the full owner/account tuple; never use caller-provided path
            # segments and never share a database between accounts.
            identity = "\\0".join(key).encode("utf-8")
            filename = hashlib.sha256(identity).hexdigest() + ".sqlite3"
            store = MT5RelayStore(self.runtime_dir / filename, expected_source_id=source_id)
            self._stores[key] = store
        elif store.expected_source_id != source_id:
            raise PermissionError("source id provisionado mudou; exige reprovisionamento controlado")
        return key, store

    def ingest(
        self, context: TenantContext, connection_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        _, store = self._resolve(context, connection_id)
        # MT5RelayStore independently enforces DEMO, freshness, UUID replay
        # protection, candle validity, and the server-provisioned source id.
        return store.ingest(payload)

    def fetch(
        self, context: TenantContext, connection_id: str, request: MarketDataRequest
    ):
        _, store = self._resolve(context, connection_id)
        store.get_account_mode()
        return store.fetch(request)

    def status(self, context: TenantContext, connection_id: str) -> dict[str, Any]:
        _, store = self._resolve(context, connection_id)
        return store.status()
