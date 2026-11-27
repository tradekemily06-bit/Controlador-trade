from __future__ import annotations

import math
import re
from typing import Any, Callable, Mapping
from security.push_subscription_registry import _validate_endpoint


class VapidConfigurationError(RuntimeError):
    """VAPID sender configuration is incomplete or unsafe."""


class PyWebPushSender:
    """Synchronous Web Push sender backed by pywebpush and an injected secret source.

    The private key is fetched for each send from the host's secret manager.
    It is never accepted from a request, persisted by this class, or logged.
    """

    def __init__(
        self,
        private_key_provider: Callable[[], str],
        *,
        subject: str,
        timeout_seconds: float = 10.0,
        webpush_function: Callable[..., Any] | None = None,
    ) -> None:
        if not callable(private_key_provider):
            raise ValueError("private_key_provider must be callable")
        if not isinstance(subject, str) or not re.fullmatch(r"mailto:[^\s@]+@[^\s@]+", subject):
            raise ValueError("VAPID subject must be a mailto contact address")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("timeout_seconds must be a positive finite number")
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("timeout_seconds must be a finite number between 0 and 30")
        self._private_key_provider = private_key_provider
        self.subject = subject
        self.timeout_seconds = float(timeout_seconds)
        self._webpush_function = webpush_function

    def _webpush(self) -> Callable[..., Any]:
        if self._webpush_function is not None:
            return self._webpush_function
        try:
            from pywebpush import webpush
        except ImportError as exc:
            raise RuntimeError("pywebpush dependency is not installed") from exc
        return webpush

    def __call__(
        self,
        subscription_info: Mapping[str, Any],
        payload_json: str,
        *,
        ttl_seconds: int,
        idempotency_key: str,
    ) -> Any:
        if not isinstance(subscription_info, Mapping):
            raise ValueError("subscription_info must be an object")
        endpoint = subscription_info.get("endpoint")
        if not isinstance(endpoint, str):
            raise ValueError("subscription endpoint must be an approved HTTPS browser push service")
        _validate_endpoint(endpoint)
        if not isinstance(payload_json, str) or not payload_json:
            raise ValueError("payload_json is required")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 0 <= ttl_seconds <= 2419200:
            raise ValueError("ttl_seconds is outside the Web Push TTL range")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")

        private_key = self._private_key_provider()
        if not isinstance(private_key, str) or not private_key.strip():
            raise VapidConfigurationError("VAPID private key is unavailable")
        # pywebpush accepts a base64-encoded DER key string or a PEM file path.
        # Paths are intentionally forbidden here; only secret-managed DER
        # material is accepted, so the library cannot read arbitrary host files.
        if not re.fullmatch(r"[A-Za-z0-9_+/=-]{40,}", private_key.strip()):
            raise VapidConfigurationError("VAPID private key must be base64-encoded DER material")

        claims = {"sub": self.subject}
        # pywebpush derives aud from each endpoint and refreshes exp when absent.
        return self._webpush()(
            subscription_info=dict(subscription_info),
            data=payload_json,
            vapid_private_key=private_key,
            vapid_claims=claims,
            ttl=ttl_seconds,
            timeout=self.timeout_seconds,
            verbose=False,
        )



def build_tenant_web_push_sink(
    store: Any,
    private_key_provider: Callable[[], str],
    *,
    subject: str,
    ttl_seconds: int = 300,
    timeout_seconds: float = 10.0,
) -> Any:
    """Compose the tenant-isolated sink with the host-configured VAPID sender.

    This factory deliberately requires the caller to inject the durable,
    encrypted subscription store and secret-manager callback. It does not
    discover credentials from environment variables or enable a global sender.
    """
    from integration.tenant_web_push_notification_sink import TenantWebPushNotificationSink

    sender = PyWebPushSender(
        private_key_provider,
        subject=subject,
        timeout_seconds=timeout_seconds,
    )
    return TenantWebPushNotificationSink(store, sender, ttl_seconds=ttl_seconds)



def build_tenant_web_push_components(
    store: Any,
    private_key_provider: Callable[[], str],
    *,
    subject: str,
    ttl_seconds: int = 300,
    timeout_seconds: float = 10.0,
) -> tuple[Any, Any]:
    """Build the matching registry and delivery sink for StandaloneRuntime.

    Pass the returned registry as tenant_push_subscription_registry and the
    returned sink as tenant_notification_sink. Both components share the exact
    same encrypted store instance; no browser or global recipient is trusted.
    """
    from security.push_subscription_registry import TenantPushSubscriptionRegistry

    registry = TenantPushSubscriptionRegistry(store)
    sink = build_tenant_web_push_sink(
        store,
        private_key_provider,
        subject=subject,
        ttl_seconds=ttl_seconds,
        timeout_seconds=timeout_seconds,
    )
    return registry, sink
