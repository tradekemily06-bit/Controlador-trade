from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from security.tenant_context import TenantContext


class DurableAuditBoundary(ABC):
    """Provider-neutral contract for production-durable tenant audit storage.

    Production durability must come from an external, durable, multi-instance
    persistence implementation. In-memory or process-local sinks must never
    claim readiness for production.
    """

    production_durable: bool = False

    @abstractmethod
    def record(self, context: TenantContext, event: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self, context: TenantContext) -> list[dict[str, Any]]:
        raise NotImplementedError

    @property
    def ready_for_production(self) -> bool:
        return bool(self.production_durable)


def require_durable_audit(boundary: DurableAuditBoundary | None) -> DurableAuditBoundary:
    """Fail closed when durable production audit is not configured."""
    if boundary is None or not boundary.ready_for_production:
        raise RuntimeError("durable production audit is not configured")
    return boundary
