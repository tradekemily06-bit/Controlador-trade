from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from security_audit import SecurityEvent


class TenantAuditSink(Protocol):
    """Provider-neutral contract for tenant-scoped security audit storage."""

    def record(self, *, tenant_id: str, event: SecurityEvent) -> None:
        ...

    def snapshot(self, *, tenant_id: str) -> list[dict[str, object]]:
        ...


class TenantAuditBoundary:
    """Require an explicit tenant scope before audit data is persisted or read.

    Authentication and tenant resolution stay outside this boundary. The caller must
    supply the trusted tenant identity obtained from the deployment identity layer.
    """

    @staticmethod
    def _validate_tenant(tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        return tenant_id.strip()

    def __init__(self, sink: TenantAuditSink) -> None:
        self.sink = sink

    def record(self, *, tenant_id: str, event: SecurityEvent) -> None:
        tenant = self._validate_tenant(tenant_id)
        if not isinstance(event, SecurityEvent):
            raise TypeError("event must be a SecurityEvent")
        self.sink.record(tenant_id=tenant, event=event)

    def snapshot(self, *, tenant_id: str) -> list[dict[str, object]]:
        tenant = self._validate_tenant(tenant_id)
        return [dict(item) for item in self.sink.snapshot(tenant_id=tenant)]


class InMemoryTenantAuditSink:
    """Small deterministic test/demo sink; not a production persistence provider."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, object]]] = {}

    def record(self, *, tenant_id: str, event: SecurityEvent) -> None:
        self._events.setdefault(tenant_id, []).append(asdict(event))

    def snapshot(self, *, tenant_id: str) -> list[dict[str, object]]:
        return [dict(item) for item in self._events.get(tenant_id, [])]
