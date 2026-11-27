from __future__ import annotations

from dataclasses import dataclass


_MAX_ID_LENGTH = 256


def _canonical_identity_component(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > _MAX_ID_LENGTH:
        raise ValueError(f"{field} must contain at most {_MAX_ID_LENGTH} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{field} cannot contain control characters")
    return normalized


@dataclass(frozen=True)
class TenantContext:
    """Immutable, canonical tenant context for SaaS boundaries.

    This value object does not authenticate callers. Remote callers must obtain
    it only from the trusted server-side identity middleware boundary.
    """

    tenant_id: str
    subject_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "tenant_id", _canonical_identity_component(self.tenant_id, "tenant_id")
        )
        object.__setattr__(
            self, "subject_id", _canonical_identity_component(self.subject_id, "subject_id")
        )

    @property
    def key(self) -> str:
        return (
            f"tenant:{len(self.tenant_id)}:{self.tenant_id}:"
            f"subject:{len(self.subject_id)}:{self.subject_id}"
        )


def build_trusted_tenant_context(
    *, authenticated: bool, tenant_id: str | None, subject_id: str | None
) -> TenantContext | None:
    """Create context only from an already-authenticated deployment boundary."""
    if not authenticated or not isinstance(tenant_id, str) or not isinstance(subject_id, str):
        return None
    try:
        return TenantContext(tenant_id=tenant_id, subject_id=subject_id)
    except ValueError:
        return None
