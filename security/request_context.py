from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionRequestContext:
    """Trusted, provider-neutral context required by production operations."""

    subject_id: str
    tenant_id: str

    def is_valid(self) -> bool:
        return bool(self.subject_id.strip() and self.tenant_id.strip())

    def status(self) -> dict[str, str]:
        return {
            "authenticated": "YES" if self.is_valid() else "NO",
            "tenant_scope": "SET" if self.tenant_id.strip() else "MISSING",
        }


def require_production_context(*, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
    """Fail closed when a production request has no trusted subject/tenant."""
    if not subject_id or not subject_id.strip():
        raise PermissionError("production subject is required")
    if not tenant_id or not tenant_id.strip():
        raise PermissionError("production tenant is required")
    return ProductionRequestContext(subject_id=subject_id.strip(), tenant_id=tenant_id.strip())
