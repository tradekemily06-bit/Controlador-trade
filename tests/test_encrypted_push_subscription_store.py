import os

import pytest

from security.encrypted_push_subscription_store import EncryptedTenantPushSubscriptionStore
from security.tenant_context import TenantContext


class DurableBackend:
    production_durable = True

    def __init__(self):
        self.rows = {}

    def _scope(self, context, key):
        return (context.tenant_id, context.subject_id, key)

    def get(self, context, key):
        return self.rows.get(self._scope(context, key))

    def put(self, context, key, value):
        self.rows[self._scope(context, key)] = value

    def delete(self, context, key):
        self.rows.pop(self._scope(context, key), None)

    def list_keys(self, context, prefix):
        return [
            key for (tenant, subject, key) in self.rows
            if tenant == context.tenant_id and subject == context.subject_id and key.startswith(prefix)
        ]


class LocalBackend(DurableBackend):
    production_durable = False


def _record(endpoint="https://fcm.googleapis.com/fcm/send/token"):
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
        "status": "ACTIVE",
        "expiration_time": None,
    }


def test_encrypts_records_and_round_trips_only_for_exact_owner():
    backend = DurableBackend()
    store = EncryptedTenantPushSubscriptionStore(backend, lambda: b"k" * 32)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")

    store.put_for_owner(alice, "phone-1", _record())
    raw = backend.get(alice, "push-subscription:v1:phone-1")
    assert "endpoint" not in str(raw)
    assert "auth-secret" not in str(raw)
    assert store.list_for_owner(alice) == [{**_record(), "device_id": "phone-1"}]
    assert store.list_for_owner(bob) == []


def test_authentication_detects_ciphertext_tampering_and_wrong_owner():
    backend = DurableBackend()
    store = EncryptedTenantPushSubscriptionStore(backend, lambda: b"k" * 32)
    owner = TenantContext("tenant-a", "alice")
    store.put_for_owner(owner, "phone-1", _record())
    key = "push-subscription:v1:phone-1"
    envelope = backend.get(owner, key)
    envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"
    backend.put(owner, key, envelope)
    with pytest.raises(RuntimeError, match="could not be authenticated"):
        store.list_for_owner(owner)


def test_requires_durable_backend_and_secret_managed_32_byte_key():
    with pytest.raises(RuntimeError, match="production-durable"):
        EncryptedTenantPushSubscriptionStore(LocalBackend(), lambda: b"k" * 32)
    store = EncryptedTenantPushSubscriptionStore(DurableBackend(), lambda: b"short")
    with pytest.raises(RuntimeError, match="32 secret-managed bytes"):
        store.put_for_owner(TenantContext("t", "s"), "device", _record())


def test_delete_is_owner_scoped_and_validates_device_id():
    backend = DurableBackend()
    store = EncryptedTenantPushSubscriptionStore(backend, lambda: b"k" * 32)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    store.put_for_owner(alice, "phone-1", _record())
    assert store.delete_for_owner(bob, "phone-1") is False
    assert store.delete_for_owner(alice, "phone-1") is True
    with pytest.raises(ValueError):
        store.put_for_owner(alice, "../other-tenant", _record())
