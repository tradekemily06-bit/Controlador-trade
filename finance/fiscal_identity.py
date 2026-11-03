"""Canonical single-user owner identity for fiscal data.

The owner is derived only from server configuration, never from request payloads,
query parameters, browser state, or caller-supplied identity strings. Callers must
complete the existing request authorization before resolving this value.
"""
from __future__ import annotations

import hashlib
import os


_ENV_NAME = "CONTROLADOR_SINGLE_USER_IDENTITY"
_DOMAIN_SEPARATOR = b"controlador-trading:fiscal-owner:v1:"


class FiscalOwnerIdentityError(RuntimeError):
    """Raised when the server cannot establish its configured fiscal owner."""


def configured_fiscal_owner_id() -> str:
    """Return a stable opaque owner key shared by authorized local/remote access.

    Local requests and remote requests authenticated against the configured
    single-user identity intentionally resolve to the same key. The raw
    configured identity is never persisted in fiscal tables.
    """
    configured = os.getenv(_ENV_NAME, "").strip().casefold()
    if not configured:
        raise FiscalOwnerIdentityError(
            f"{_ENV_NAME} precisa estar configurada antes de acessar ou migrar dados fiscais"
        )
    digest = hashlib.sha256(_DOMAIN_SEPARATOR + configured.encode("utf-8")).hexdigest()
    return f"single:{digest}"
