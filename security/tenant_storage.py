from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from security.tenant_context import TenantContext


class TenantStorageBoundary(ABC):
    """Provider-neutral contract for tenant-scoped durable storage.

    Implementations must never accept a missing or malformed tenant context.
    Local or in-memory implementations must not claim production durability
    merely by implementing this interface.
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
    """Require a canonical context object supplied by the trusted auth boundary.

    This validates the context's shape; it does not authenticate the caller.
    Remote authentication and context construction remain the responsibility
    of the trusted server-side identity middleware.
    """
    if type(context) is not TenantContext:
        raise PermissionError("trusted tenant context is required")
    for value in (context.tenant_id, context.subject_id):
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise PermissionError("canonical tenant context is required")
    return context
