from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from integration.pywebpush_sender import PyWebPushSender
from integration.tenant_web_push_notification_sink import TenantWebPushNotificationSink
from security.encrypted_push_subscription_store import (
    DurableTenantRecordBackend,
    EncryptedTenantPushSubscriptionStore,
)
from security.push_subscription_registry import TenantPushSubscriptionRegistry


@dataclass(frozen=True)
class TenantWebPushComponents:
    """Matched registration and delivery components sharing one encrypted store."""

    subscription_registry: TenantPushSubscriptionRegistry
    notification_sink: TenantWebPushNotificationSink


def build_tenant_web_push_components(
    backend: DurableTenantRecordBackend,
    *,
    encryption_key_provider: Callable[[], bytes],
    vapid_private_key_provider: Callable[[], str],
    vapid_subject: str,
    ttl_seconds: int = 300,
    timeout_seconds: float = 10.0,
) -> TenantWebPushComponents:
    """Build secure subscription registration and outbox delivery components.

    The caller must supply real host-managed secrets and a backend whose
    production_durable declaration is backed by operational evidence. This
    factory never reads secrets from environment variables or starts workers.
    Pass the returned notification_sink to StandaloneRuntime only after the
    host has completed its own deployment readiness checks.
    """
    # Fail during composition rather than after the first user attempts to
    # subscribe. The key remains supplied by the host secret manager and is
    # never retained by this factory.
    encryption_key = encryption_key_provider()
    if not isinstance(encryption_key, bytes) or len(encryption_key) != 32:
        raise RuntimeError("push subscription encryption key must be 32 secret-managed bytes")
    store = EncryptedTenantPushSubscriptionStore(
        backend,
        encryption_key_provider,
    )
    registry = TenantPushSubscriptionRegistry(store)
    sender = PyWebPushSender(
        vapid_private_key_provider,
        subject=vapid_subject,
        timeout_seconds=timeout_seconds,
    )
    sink = TenantWebPushNotificationSink(
        store,
        sender,
        ttl_seconds=ttl_seconds,
    )
    return TenantWebPushComponents(
        subscription_registry=registry,
        notification_sink=sink,
    )
