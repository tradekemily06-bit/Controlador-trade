from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    """Immutable tenant context for provider-neutral SaaS boundaries."""

    tenant_id: str
    subject_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.subject_id.strip():
            raise ValueError("subject_id is required")

    @property
    def key(self) -> str:
        return f"tenant:{self.tenant_id.strip()}:subject:{self.subject_id.strip()}"


def build_trusted_tenant_context(*, authenticated: bool, tenant_id: str | None, subject_id: str | None) -> TenantContext | None:
    """Create context only from an already-authenticated deployment boundary."""
    if not authenticated or not tenant_id or not subject_id:
        return None
    if not tenant_id.strip() or not subject_id.strip():
        return None
    return TenantContext(tenant_id=tenant_id, subject_id=subject_id)
