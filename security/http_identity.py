from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass

from storage.production_provider import ProductionProviderConfig, build_production_provider


SAAS_PUBLIC_ENV = "CONTROLADOR_SAAS_PUBLIC"
TRUSTED_SUBJECT_KEY = "controlador.trusted_subject_id"
TRUSTED_TENANT_KEY = "controlador.trusted_tenant_id"
TRUSTED_ROLE_KEY = "controlador.trusted_role"
MAX_IDENTITY_COMPONENT_LENGTH = 256
MAX_ROLE_LENGTH = 64


class PublicSaaSNotReady(RuntimeError):
    """Raised when public SaaS is requested without a real tenant-scoped data plane."""


@dataclass(frozen=True)
class TrustedHttpIdentity:
    """Identity injected by trusted deployment middleware, never by browser headers."""

    subject_id: str
    tenant_id: str
    role: str

    def is_valid(self) -> bool:
        values = (self.subject_id, self.tenant_id, self.role)
        if not all(isinstance(value, str) and value.strip() for value in values):
            return False
        if len(self.subject_id.strip()) > MAX_IDENTITY_COMPONENT_LENGTH:
            return False
        if len(self.tenant_id.strip()) > MAX_IDENTITY_COMPONENT_LENGTH:
            return False
        if len(self.role.strip()) > MAX_ROLE_LENGTH:
            return False
        if any(ord(char) < 32 for value in values for char in value):
            return False
        return True


_current_identity: ContextVar[TrustedHttpIdentity | None] = ContextVar("controlador_trusted_identity", default=None)


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
    """Fail closed for public SaaS requests without a deployment-trusted identity.

    The infrastructure health endpoint is intentionally public and carries no
    user or tenant state. It gets a synthetic non-user identity only so the
    common request path can continue without treating health as authenticated.
    """
    if str(environ.get("PATH_INFO", "")) == "/api/health":
        identity = TrustedHttpIdentity("health-check", "health-check", "health")
        _current_identity.set(identity)
        return identity
    identity = resolve_trusted_identity(environ)
    if identity is None:
        raise PermissionError("trusted identity is required")
    _current_identity.set(identity)
    return identity


def current_trusted_identity() -> TrustedHttpIdentity | None:
    """Return the identity established by the trusted HTTP boundary for this request."""
    return _current_identity.get()


def clear_trusted_identity() -> None:
    """Clear request identity after request completion in long-lived worker contexts."""
    _current_identity.set(None)


def require_role(identity: TrustedHttpIdentity, *allowed_roles: str) -> None:
    allowed = {role.strip().lower() for role in allowed_roles}
    if identity.role not in allowed:
        raise PermissionError("insufficient role")


def require_tenant_scoped_data_plane() -> None:
    """Require durable production storage scoped to the trusted request identity.

    The tenant and subject are taken from the server-established identity for
    this request. They are never synthesized from deployment configuration or
    accepted from browser-controlled HTTP headers.
    """
    identity = current_trusted_identity()
    if identity is None or identity.subject_id == "health-check" or identity.tenant_id == "health-check":
        raise PublicSaaSNotReady("trusted user identity is required for tenant-scoped data plane")

    cfg = ProductionProviderConfig.from_environment()
    try:
        provider, policy = build_production_provider(cfg)
    except (RuntimeError, ValueError) as exc:
        raise PublicSaaSNotReady("tenant-scoped data plane is not safely configured") from exc
    if provider is None or not cfg.database_path:
        raise PublicSaaSNotReady("tenant-scoped data plane is not configured")
    if not policy.authorize_write(
        authenticated=True,
        tenant_id=identity.tenant_id,
        subject_id=identity.subject_id,
    ):
        raise PublicSaaSNotReady("tenant-and-subject-scoped data plane is not authorized")
    if not policy.durable or not policy.tenant_scoped or not policy.subject_scoped:
        raise PublicSaaSNotReady("tenant-and-subject-scoped data plane must be durable and scoped")
