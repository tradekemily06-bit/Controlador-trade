from __future__ import annotations

import os
from dataclasses import dataclass


SAAS_PUBLIC_ENV = "CONTROLADOR_SAAS_PUBLIC"
TRUSTED_SUBJECT_KEY = "controlador.trusted_subject_id"
TRUSTED_TENANT_KEY = "controlador.trusted_tenant_id"
TRUSTED_ROLE_KEY = "controlador.trusted_role"


class PublicSaaSNotReady(RuntimeError):
    """Raised when public SaaS is requested without a real tenant-scoped data plane."""


@dataclass(frozen=True)
class TrustedHttpIdentity:
    """Identity injected by trusted deployment middleware, never by browser headers."""

    subject_id: str
    tenant_id: str
    role: str

    def is_valid(self) -> bool:
        return bool(self.subject_id.strip() and self.tenant_id.strip() and self.role.strip())


def saas_public_mode() -> bool:
    return os.environ.get(SAAS_PUBLIC_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_trusted_identity(environ) -> TrustedHttpIdentity | None:
    """Resolve only server-injected WSGI keys; HTTP X-* headers are intentionally ignored."""
    subject_id = environ.get(TRUSTED_SUBJECT_KEY)
    tenant_id = environ.get(TRUSTED_TENANT_KEY)
    role = environ.get(TRUSTED_ROLE_KEY)
    if not all(isinstance(value, str) and value.strip() for value in (subject_id, tenant_id, role)):
        return None
    identity = TrustedHttpIdentity(subject_id.strip(), tenant_id.strip(), role.strip().lower())
    return identity if identity.is_valid() else None


def require_trusted_identity(environ) -> TrustedHttpIdentity:
    """Fail closed for public SaaS requests without a deployment-trusted identity."""
    identity = resolve_trusted_identity(environ)
    if identity is None:
        raise PermissionError("trusted identity is required")
    return identity


def require_role(identity: TrustedHttpIdentity, *allowed_roles: str) -> None:
    allowed = {role.strip().lower() for role in allowed_roles}
    if identity.role not in allowed:
        raise PermissionError("insufficient role")


def require_tenant_scoped_data_plane() -> None:
    """Public SaaS must not expose process-global state as if it were tenant-isolated."""
    raise PublicSaaSNotReady("tenant-scoped data plane is not configured")
