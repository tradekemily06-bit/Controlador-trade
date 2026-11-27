import base64
import json

import pytest

from integration.tenant_web_push_notification_sink import (
    NoActivePushSubscriptions,
    TenantWebPushNotificationSink,
    WebPushDeliveryError,
)


class SecureStore:
    production_durable = True
    encrypted_at_rest = True

    def __init__(self, records=None):
        self.records = list(records or [])
        self.deleted = []

    def list_for_owner(self, context):
        self.last_owner = (context.tenant_id, context.subject_id)
        return list(self.records)

    def delete_for_owner(self, context, device_id):
        self.deleted.append((context.tenant_id, context.subject_id, device_id))
        self.records = [item for item in self.records if item.get("device_id") != device_id]
        return True


class LocalStore(SecureStore):
    production_durable = False


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _record(device_id="phone-1", endpoint="https://fcm.googleapis.com/fcm/send/token"):
    return {
        "device_id": device_id,
        "status": "ACTIVE",
        "endpoint": endpoint,
        "keys": {"p256dh": _b64(b"\x04" + bytes(range(1, 65))), "auth": _b64(bytes(range(16)))},
    }


def _payload():
    return {
        "notification_id": "event-1",
        "title": "Sinal atualizado",
        "message": "EURUSD M5: AGUARDAR",
        "kind": "MARKET_SIGNAL",
        "severity": "INFO",
        "internal_secret": "must-not-leave-server",
    }


def test_requires_durable_encrypted_store_and_sender():
    with pytest.raises(RuntimeError, match="production-durable"):
        TenantWebPushNotificationSink(LocalStore(), lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="sender"):
        TenantWebPushNotificationSink(SecureStore(), None)


def test_delivers_only_to_explicit_owner_and_filters_payload():
    store = SecureStore([_record()])
    sent = []

    def sender(subscription, data, **kwargs):
        sent.append((subscription, json.loads(data), kwargs))

    sink = TenantWebPushNotificationSink(store, sender)
    sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, _payload())

    assert len(sent) == 1
    assert store.last_owner == ("tenant-a", "alice")
    assert sent[0][0]["endpoint"] == "https://fcm.googleapis.com/fcm/send/token"
    assert sent[0][1]["idempotency_key"] == "idem-1"
    assert "internal_secret" not in sent[0][1]
    assert sent[0][2]["ttl_seconds"] == 300


def test_rejects_missing_recipient_and_no_subscriptions():
    sink = TenantWebPushNotificationSink(SecureStore(), lambda *args, **kwargs: None)
    with pytest.raises(PermissionError):
        sink.deliver("idem-1", {}, _payload())
    with pytest.raises(NoActivePushSubscriptions):
        sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, _payload())


def test_removes_only_expired_404_410_subscription():
    store = SecureStore([_record()])

    class Gone(Exception):
        status_code = 410

    def sender(*args, **kwargs):
        raise Gone()

    sink = TenantWebPushNotificationSink(store, sender)
    with pytest.raises(NoActivePushSubscriptions):
        sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, _payload())
    assert store.deleted == [("tenant-a", "alice", "phone-1")]


def test_transient_sender_error_is_redacted_and_retried_by_outbox():
    store = SecureStore([_record()])

    class ProviderFailure(Exception):
        pass

    def sender(*args, **kwargs):
        raise ProviderFailure("contains endpoint token")

    sink = TenantWebPushNotificationSink(store, sender)
    with pytest.raises(WebPushDeliveryError) as error:
        sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, _payload())
    assert "endpoint token" not in str(error.value)


def test_rejects_unsafe_persisted_endpoint_and_oversized_payload():
    store = SecureStore([_record(endpoint="https://attacker.example.test/push")])
    sink = TenantWebPushNotificationSink(store, lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="approved HTTPS"):
        sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, _payload())

    store = SecureStore([_record()])
    sink = TenantWebPushNotificationSink(store, lambda *args, **kwargs: None)
    huge = _payload()
    huge["message"] = "x" * 4000
    with pytest.raises(ValueError, match="3500-byte"):
        sink.deliver("idem-1", {"tenant_id": "tenant-a", "subject_id": "alice"}, huge)
