import pytest

from integration.tenant_web_push_factory import build_tenant_web_push_components
from integration.tenant_web_push_notification_sink import TenantWebPushNotificationSink
from security.push_subscription_registry import TenantPushSubscriptionRegistry


class DurableBackend:
    production_durable = True

    def __init__(self):
        self.rows = {}

    def get(self, context, key):
        return self.rows.get((context.tenant_id, context.subject_id, key))

    def put(self, context, key, value):
        self.rows[(context.tenant_id, context.subject_id, key)] = value

    def delete(self, context, key):
        self.rows.pop((context.tenant_id, context.subject_id, key), None)

    def list_keys(self, context, prefix):
        return [
            key for tenant, subject, key in self.rows
            if tenant == context.tenant_id and subject == context.subject_id and key.startswith(prefix)
        ]


class LocalBackend(DurableBackend):
    production_durable = False


def test_factory_shares_encrypted_store_between_registry_and_sink():
    components = build_tenant_web_push_components(
        DurableBackend(),
        encryption_key_provider=lambda: b"k" * 32,
        vapid_private_key_provider=lambda: "A" * 48,
        vapid_subject="mailto:ops@example.com",
    )
    assert isinstance(components.subscription_registry, TenantPushSubscriptionRegistry)
    assert isinstance(components.notification_sink, TenantWebPushNotificationSink)
    assert components.subscription_registry.store is components.notification_sink.store


def test_factory_fails_closed_for_local_backend_and_missing_secrets():
    with pytest.raises(RuntimeError, match="production-durable"):
        build_tenant_web_push_components(
            LocalBackend(),
            encryption_key_provider=lambda: b"k" * 32,
            vapid_private_key_provider=lambda: "A" * 48,
            vapid_subject="mailto:ops@example.com",
        )

    with pytest.raises(RuntimeError, match="32 secret-managed bytes"):
        build_tenant_web_push_components(
            DurableBackend(),
            encryption_key_provider=lambda: b"short",
            vapid_private_key_provider=lambda: "A" * 48,
            vapid_subject="mailto:ops@example.com",
        )
