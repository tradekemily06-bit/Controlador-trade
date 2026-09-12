from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProductionStore(Protocol):
    """Provider-neutral contract for durable, tenant-scoped production state."""

    def save(self, record: dict[str, Any], *, tenant_id: str) -> None:
        ...

    def load(self, record_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        ...

    def list(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class ProductionStoragePolicy:
    """Fail-closed policy for production persistence readiness."""

    required: bool = True
    provider_configured: bool = False
    tenant_scoped: bool = True
    durable: bool = False

    def status(self) -> dict[str, object]:
        if not self.required:
            state = "OPTIONAL"
        elif not self.provider_configured:
            state = "NOT_CONFIGURED"
        elif not self.tenant_scoped:
            state = "UNSAFE_TENANT_SCOPE"
        elif not self.durable:
            state = "NOT_DURABLE"
        else:
            state = "READY"
        return {
            "required": self.required,
            "provider": "CONFIGURED" if self.provider_configured else "NOT_CONFIGURED",
            "tenant_scope": "ENFORCED" if self.tenant_scoped else "NOT_ENFORCED",
            "durability": "DURABLE" if self.durable else "NOT_DURABLE",
            "state": state,
        }

    def authorize_write(self, *, authenticated: bool, tenant_id: str | None) -> bool:
        if not self.required:
            return True
        return bool(authenticated and tenant_id and tenant_id.strip() and self.provider_configured and self.tenant_scoped and self.durable)

    def authorize_read(self, *, authenticated: bool, tenant_id: str | None) -> bool:
        return self.authorize_write(authenticated=authenticated, tenant_id=tenant_id)


class UnconfiguredProductionStore:
    """Explicit fail-closed placeholder until deployment supplies a real provider."""

    def save(self, record: dict[str, Any], *, tenant_id: str) -> None:
        raise RuntimeError("production storage provider is not configured")

    def load(self, record_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        raise RuntimeError("production storage provider is not configured")

    def list(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        raise RuntimeError("production storage provider is not configured")
