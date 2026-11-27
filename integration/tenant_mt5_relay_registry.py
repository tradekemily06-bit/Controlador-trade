"""Tenant/account-isolated MT5 relay stores.

The HTTP authentication layer must resolve the relay token to a trusted
TenantContext before calling this service. Client payloads never select a
tenant, account, database path, or expected source id.
"""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Any, Callable

from data.feed import MarketDataRequest
from integration.mt5_relay_store import MT5RelayStore
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


class _TenantMT5RelayMarketDataAdapter:
    """Read-only adapter bound to exactly one tenant/account relay store."""

    def __init__(self, store: MT5RelayStore) -> None:
        self.store = store

    def fetch(self, request: MarketDataRequest):
        self.store.get_account_mode()
        return self.store.fetch(request)

    def status(self) -> dict[str, Any]:
        return self.store.status()

    def disconnect(self) -> None:
        # The relay is an inbound/outbound agent relationship; no local socket
        # is held by this adapter. Token revocation is handled by the vault.
        return None


class TenantMT5RelayRegistry:
    """Resolve one durable DEMO relay store per verified tenant connection."""

    def __init__(
        self,
        connections: Any,
        runtime_dir: str | Path,
        source_id_resolver: Callable[[TenantContext, str], str],
        *, sessions: Any | None = None,
    ) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        if not callable(source_id_resolver):
            raise ValueError("trusted source_id_resolver is required")
        self.connections = connections
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.source_id_resolver = source_id_resolver
        self.sessions = sessions
        self._stores: dict[tuple[str, str, str], MT5RelayStore] = {}
        self._adapters: dict[tuple[str, str, str], _TenantMT5RelayMarketDataAdapter] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _connection_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("connection_id inválido")
        return value

    def _resolve(self, context: TenantContext, connection_id: str, *, allow_pending: bool = False) -> tuple[tuple[str, str, str], MT5RelayStore]:
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
        allowed_statuses = {"CONNECTED", "PENDING"} if allow_pending else {"CONNECTED"}
        if account.get("status") not in allowed_statuses:
            raise PermissionError("conexão MT5 precisa de provisionamento/handshake vigente")
        source_id = self.source_id_resolver(owner, connection)
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", source_id):
            raise PermissionError("origem MT5 não provisionada pelo servidor")
        key = (owner.tenant_id, owner.subject_id, connection)
        with self._lock:
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
        owner = require_tenant_context(context)
        _, store = self._resolve(owner, connection_id, allow_pending=True)
        account = next((
            item for item in self.connections.list_connections(owner)
            if item["connection_id"] == connection_id
        ), None)
        if account is None or account.get("provider_id") != "mt5_relay":
            raise PermissionError("conexão MT5 não pertence a esta identidade")
        account_reference = payload.get("account_reference") if isinstance(payload, dict) else None
        if not isinstance(account_reference, str) or not re.fullmatch(r"mt5_[a-f0-9]{32}", account_reference):
            raise PermissionError("referência pseudônima da conta MT5 ausente ou inválida")
        if account.get("status") == "CONNECTED" and account.get("account_reference") != account_reference:
            raise PermissionError("o terminal MT5 não corresponde à conta vinculada a esta conexão")
        # The first valid, fresh DEMO batch binds the actual terminal identity.
        result = store.ingest(payload)
        if account.get("status") == "PENDING":
            promoted = self.connections.mark_connected_after_provider_handshake(
                owner,
                connection_id=connection_id,
                account_reference=account_reference,
                capabilities=["candles:read", "account-mode:demo"],
            )
            if not promoted:
                raise PermissionError("conexão MT5 não pôde ser promovida após o handshake")
        if self.sessions is not None:
            owner = require_tenant_context(context)
            key = (owner.tenant_id, owner.subject_id, connection_id)
            with self._lock:
                adapter = self._adapters.get(key)
                if adapter is None:
                    adapter = _TenantMT5RelayMarketDataAdapter(store)
                    self._adapters[key] = adapter
            self.sessions.bind(
                owner, connection_id=connection_id, adapter=adapter,
                source=f"mt5_relay:{connection_id}", handshake_verified=True,
            )
        return result

    def fetch(
        self, context: TenantContext, connection_id: str, request: MarketDataRequest
    ):
        _, store = self._resolve(context, connection_id)
        store.get_account_mode()
        return store.fetch(request)

    def status(self, context: TenantContext, connection_id: str) -> dict[str, Any]:
        _, store = self._resolve(context, connection_id)
        return store.status()
