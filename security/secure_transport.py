from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransportSecurityStatus:
    """Deployment-level transport posture; defaults to fail-closed."""

    tls_enabled: bool = False
    trusted_proxy_configured: bool = False

    @property
    def ready_for_production(self) -> bool:
        return self.tls_enabled and self.trusted_proxy_configured


def require_secure_transport(status: TransportSecurityStatus | None) -> TransportSecurityStatus:
    """Fail closed unless production transport prerequisites are configured."""
    if status is None or not status.ready_for_production:
        raise RuntimeError("secure production transport is not configured")
    return status
