from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os


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


def _trusted_proxy_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    raw = os.environ.get("CONTROLADOR_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return ()
    networks: list[ipaddress._BaseNetwork] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        networks.append(ipaddress.ip_network(value, strict=False))
    return tuple(networks)


def is_trusted_proxy(remote_addr: str | None) -> bool:
    """Return true only when REMOTE_ADDR belongs to an explicitly trusted proxy."""
    if not remote_addr:
        return False
    try:
        address = ipaddress.ip_address(remote_addr.strip())
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def request_uses_tls(environ) -> bool:
    """Determine HTTPS only from the direct connection or a trusted proxy header."""
    scheme = str(environ.get("wsgi.url_scheme", "")).lower()
    if scheme == "https":
        return True
    if not is_trusted_proxy(str(environ.get("REMOTE_ADDR") or "")):
        return False
    forwarded = str(environ.get("HTTP_X_FORWARDED_PROTO") or "").split(",", 1)[0].strip().lower()
    return forwarded == "https"


def production_transport_status(environ) -> TransportSecurityStatus:
    """Build a deployment status without trusting unconfigured proxy headers."""
    trusted = bool(_trusted_proxy_networks())
    return TransportSecurityStatus(tls_enabled=request_uses_tls(environ), trusted_proxy_configured=trusted)


def require_production_request_transport(environ) -> TransportSecurityStatus:
    """Fail closed for production requests unless TLS and proxy trust are explicit."""
    status = production_transport_status(environ)
    return require_secure_transport(status)
