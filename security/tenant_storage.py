from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from security.tenant_context import TenantContext


class TenantStorageBoundary(ABC):
    """Provider-neutral contract for tenant-scoped durable storage.

    Implementations must never accept a missing tenant context. Local or
    in-memory implementations must not claim production durability merely by
    implementing this interface.
    """

    production_durable: bool = False

    @abstractmethod
    def get(self, context: TenantContext, key: str) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, context: TenantContext, key: str, value: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, context: TenantContext, key: str) -> None:
        raise NotImplementedError

    @property
    def ready_for_production(self) -> bool:
        return bool(self.production_durable)


def require_tenant_context(context: TenantContext | None) -> TenantContext:
    """Fail closed when storage is accessed without trusted tenant scope."""
    if context is None:
        raise PermissionError("trusted tenant context is required")
    return context
