from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from security.tenant_context import TenantContext, build_trusted_tenant_context


def trusted_tenant_context_from_wsgi(
    environ: Mapping[str, Any],
    *,
    middleware_enabled: bool | None = None,
) -> TenantContext | None:
    """Resolve tenant scope only from verified, server-injected WSGI identity.

    REMOTE_USER is the same authenticated subject consumed by the standalone
    API authorization boundary. controlador.tenant_id and
    controlador.identity_verified must be injected by trusted middleware;
    client HTTP headers are never used as identity claims.
    """
    enabled = middleware_enabled
    if enabled is None:
        enabled = os.getenv("CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE", "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return None

    authenticated = environ.get("controlador.identity_verified") is True
    subject_id = environ.get("REMOTE_USER")
    tenant_id = environ.get("controlador.tenant_id")
    if not isinstance(subject_id, str) or not isinstance(tenant_id, str):
        return None
    return build_trusted_tenant_context(
        authenticated=authenticated,
        tenant_id=tenant_id,
        subject_id=subject_id,
    )
