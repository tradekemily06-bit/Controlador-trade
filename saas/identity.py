from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import SaaSRole, TenantContext


class IdentityRequiredError(RuntimeError):
    """Raised when a protected SaaS operation has no trusted identity."""


@dataclass(frozen=True)
class TrustedIdentity:
    """Identity already authenticated by a trusted deployment provider."""

    subject_id: str
    tenant_id: str
    role: SaaSRole


class IdentityProvider(Protocol):
    """Provider-neutral contract implemented by the deployment identity layer."""

    def resolve_identity(self) -> TrustedIdentity | None:
        ...


class IdentityBoundary:
    """Convert trusted provider identity into the application's tenant context.

    This boundary deliberately does not authenticate credentials, parse browser
    headers, manage sessions, or discover tenants. Those responsibilities remain
    with the deployment's chosen identity provider.
    """

    @staticmethod
    def _validate(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise IdentityRequiredError(f"{field} is required")
        return value.strip()

    def resolve(self, provider: IdentityProvider) -> TenantContext:
        identity = provider.resolve_identity()
        if identity is None:
            raise IdentityRequiredError("trusted identity is required")
        subject_id = self._validate(identity.subject_id, "subject_id")
        tenant_id = self._validate(identity.tenant_id, "tenant_id")
        if not isinstance(identity.role, SaaSRole):
            raise IdentityRequiredError("valid role is required")
        return TenantContext(
            subject_id=subject_id,
            tenant_id=tenant_id,
            role=identity.role,
        )
