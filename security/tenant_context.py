from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    """Immutable, canonical tenant context for SaaS boundaries."""

    tenant_id: str
    subject_id: str

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        subject_id = self.subject_id.strip()
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not subject_id:
            raise ValueError("subject_id is required")
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "subject_id", subject_id)

    @property
    def key(self) -> str:
        return f"tenant:{self.tenant_id}:subject:{self.subject_id}"


def build_trusted_tenant_context(
    *, authenticated: bool, tenant_id: str | None, subject_id: str | None
) -> TenantContext | None:
    """Create context only from an already-authenticated deployment boundary."""
    if not authenticated or not tenant_id or not subject_id:
        return None
    if not tenant_id.strip() or not subject_id.strip():
        return None
    return TenantContext(tenant_id=tenant_id, subject_id=subject_id)
