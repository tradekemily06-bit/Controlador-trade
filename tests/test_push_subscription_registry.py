import base64

import pytest

from security.push_subscription_registry import (
    PushSubscriptionInput,
    TenantPushSubscriptionRegistry,
)
from security.tenant_context import TenantContext


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class SecureStore:
    production_durable = True
    encrypted_at_rest = True

    def __init__(self):
        self.records = {}

    def put_for_owner(self, context, device_id, record):
        self.records[(context.key, device_id)] = dict(record, device_id=device_id)

    def list_for_owner(self, context):
        return [
            value for (owner, _), value in self.records.items()
            if owner == context.key
        ]

    def delete_for_owner(self, context, device_id):
        return self.records.pop((context.key, device_id), None) is not None


class LocalStore(SecureStore):
    production_durable = False


def _subscription(endpoint="https://push.example.test/send/abc"):
    return PushSubscriptionInput(
        endpoint=endpoint,
        p256dh=_b64(b"\x04" + bytes(range(1, 65))),
        auth=_b64(bytes(range(16))),
    )


def test_registry_requires_durable_encrypted_storage():
    with pytest.raises(RuntimeError, match="production-durable"):
        TenantPushSubscriptionRegistry(LocalStore())


def test_registration_is_scoped_to_tenant_and_subject_and_hides_secrets():
    store = SecureStore()
    registry = TenantPushSubscriptionRegistry(store)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")

    registry.register(alice, "phone-1", _subscription())
    assert registry.list_devices(alice) == [
        {"device_id": "phone-1", "status": "ACTIVE", "expiration_time": None}
    ]
    assert registry.list_devices(bob) == []
    assert "endpoint" not in registry.list_devices(alice)[0]
    assert "keys" not in registry.list_devices(alice)[0]


def test_registering_same_device_rotates_subscription():
    store = SecureStore()
    registry = TenantPushSubscriptionRegistry(store)
    owner = TenantContext("tenant-a", "alice")

    registry.register(owner, "phone-1", _subscription())
    registry.register(owner, "phone-1", _subscription("https://push.example.test/send/new"))
    assert len(registry.list_devices(owner)) == 1
    assert store.records[(owner.key, "phone-1")]["endpoint"].endswith("/new")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://push.example.test/send/abc",
        "https://user:password@push.example.test/send/abc",
        "https://push.example.test/send/abc#fragment",
    ],
)
def test_rejects_unsafe_push_endpoints(endpoint):
    registry = TenantPushSubscriptionRegistry(SecureStore())
    with pytest.raises(ValueError):
        registry.register(TenantContext("tenant-a", "alice"), "phone-1", _subscription(endpoint))


def test_rejects_invalid_web_push_key_lengths():
    registry = TenantPushSubscriptionRegistry(SecureStore())
    invalid = PushSubscriptionInput(
        endpoint="https://push.example.test/send/abc",
        p256dh=_b64(b"short"),
        auth=_b64(bytes(16)),
    )
    with pytest.raises(ValueError, match="p256dh"):
        registry.register(TenantContext("tenant-a", "alice"), "phone-1", invalid)


def test_revoke_and_expired_endpoint_are_owner_scoped():
    registry = TenantPushSubscriptionRegistry(SecureStore())
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    registry.register(alice, "phone-1", _subscription())

    with pytest.raises(ValueError, match="404/410"):
        registry.revoke_expired_endpoint(alice, "phone-1", http_status=500)
    assert registry.revoke(bob, "phone-1")["revoked"] is False
    assert registry.revoke_expired_endpoint(alice, "phone-1", http_status=410)["revoked"] is True


def test_registry_rejects_missing_trusted_owner():
    registry = TenantPushSubscriptionRegistry(SecureStore())
    with pytest.raises(PermissionError):
        registry.list_devices(None)
