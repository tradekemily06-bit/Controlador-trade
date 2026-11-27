"""Tenant-scoped runtime bindings between verified accounts and market-data adapters.

Adapter instances are process-local and are never serialized. A restart requires
a fresh server-side adapter handshake before an account can become usable.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context
from security.tenant_provider_connections import TenantProviderConnectionRegistry


@dataclass(frozen=True)
class TenantMarketDataSession:
    tenant_id: str
    subject_id: str
    connection_id: str
    provider_id: str
    source: str
    adapter: Any


class TenantMarketDataSessionRegistry:
    """Bind many independent provider adapters to owner-scoped account records."""

    def __init__(self, connections: TenantProviderConnectionRegistry) -> None:
        if connections is None or not callable(getattr(connections, "list_connections", None)):
            raise ValueError("tenant provider connection registry is required")
        self.connections = connections
        self._sessions: dict[tuple[str, str, str], TenantMarketDataSession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _connection_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("connection_id inválido")
        return value

    def bind(
        self,
        context: TenantContext | None,
        *,
        connection_id: str,
        adapter: Any,
        source: str,
        handshake_verified: bool,
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        key_id = self._connection_id(connection_id)
        if handshake_verified is not True:
            raise PermissionError("adapter binding requires a verified provider handshake")
        if adapter is None or not callable(getattr(adapter, "fetch", None)):
            raise ValueError("adapter must implement fetch(request)")
        if not isinstance(source, str) or not source.strip() or len(source.strip()) > 120:
            raise ValueError("source deve conter de 1 a 120 caracteres")

        account = next(
            (item for item in self.connections.list_connections(owner)
             if item["connection_id"] == key_id),
            None,
        )
        if account is None:
            raise PermissionError("connection does not belong to this tenant and subject")
        if account["status"] != "CONNECTED":
            raise PermissionError("connection must complete a fresh handshake before binding")

        key = (owner.tenant_id, owner.subject_id, key_id)
        with self._lock:
            for existing_key, session in self._sessions.items():
                if existing_key != key and session.adapter is adapter:
                    raise ValueError("one adapter instance cannot be shared across accounts")
            self._sessions[key] = TenantMarketDataSession(
                tenant_id=owner.tenant_id,
                subject_id=owner.subject_id,
                connection_id=key_id,
                provider_id=account["provider_id"],
                source=source.strip(),
                adapter=adapter,
            )
        return {
            "connection_id": key_id,
            "provider_id": account["provider_id"],
            "status": "ADAPTER_BOUND",
            "source": source.strip(),
            "read_only": True,
            "execution_authorized": False,
        }

    def get(
        self, context: TenantContext | None, *, connection_id: str
    ) -> TenantMarketDataSession | None:
        owner = require_tenant_context(context)
        key_id = self._connection_id(connection_id)
        key = (owner.tenant_id, owner.subject_id, key_id)
        with self._lock:
            return self._sessions.get(key)

    def unbind(
        self, context: TenantContext | None, *, connection_id: str
    ) -> bool:
        owner = require_tenant_context(context)
        key_id = self._connection_id(connection_id)
        key = (owner.tenant_id, owner.subject_id, key_id)
        with self._lock:
            return self._sessions.pop(key, None) is not None

    def status(self, context: TenantContext | None) -> list[dict[str, Any]]:
        owner = require_tenant_context(context)
        accounts = self.connections.list_connections(owner)
        with self._lock:
            sessions = dict(self._sessions)

        output = []
        for account in accounts:
            session = sessions.get(
                (owner.tenant_id, owner.subject_id, account["connection_id"])
            )
            health: dict[str, Any] = {}
            health_status = "NOT_BOUND"
            if session is not None:
                health_status = "UNVERIFIED"
                status_method = getattr(session.adapter, "status", None)
                if callable(status_method):
                    try:
                        reported = status_method()
                        if isinstance(reported, dict):
                            health = {
                                key: reported[key]
                                for key in (
                                    "connected", "account_mode", "last_seen", "source_id",
                                    "stored_candles", "active_spot_symbols",
                                    "spot_event_queue_depth", "spot_event_overflow_count",
                                    "last_spot_overflow_at",
                                )
                                if key in reported
                            }
                            if reported.get("connected") is False:
                                health_status = "DISCONNECTED"
                            elif reported.get("connected") is True:
                                overflow_age = float("inf")
                                raw_overflow = reported.get("last_spot_overflow_at")
                                if raw_overflow:
                                    try:
                                        overflow_at = datetime.fromisoformat(
                                            str(raw_overflow).replace("Z", "+00:00")
                                        )
                                        overflow_age = (
                                            datetime.now(timezone.utc)
                                            - overflow_at.astimezone(timezone.utc)
                                        ).total_seconds() if overflow_at.tzinfo else float("inf")
                                    except (TypeError, ValueError, OverflowError):
                                        overflow_age = float("inf")
                                if -5 <= overflow_age <= 60:
                                    health_status = "STREAM_BACKPRESSURE"
                                else:
                                    raw_seen = reported.get("last_seen")
                                    try:
                                        seen = datetime.fromisoformat(str(raw_seen).replace("Z", "+00:00"))
                                        age = (
                                            datetime.now(timezone.utc)
                                            - seen.astimezone(timezone.utc)
                                        ).total_seconds() if seen.tzinfo else float("inf")
                                    except (TypeError, ValueError, OverflowError):
                                        age = float("inf")
                                    health_status = (
                                        "CONNECTED" if -5 <= age <= 30
                                        else "HEARTBEAT_STALE_OR_UNVERIFIED"
                                    )
                    except Exception:
                        health_status = "STATUS_ERROR"
            output.append({
                "connection_id": account["connection_id"],
                "provider_id": account["provider_id"],
                "account_alias": account["account_alias"],
                "status": account["status"],
                "adapter_status": "BOUND" if session is not None else "NOT_BOUND",
                "health_status": health_status,
                "health": health,
                "read_only": True,
                "execution_authorized": False,
            })
        return output
