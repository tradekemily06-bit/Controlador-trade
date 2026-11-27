import pytest

from integration.pywebpush_sender import PyWebPushSender, VapidConfigurationError


def _subscription():
    return {
        "endpoint": "https://updates.push.services.mozilla.com/push/v1/token",
        "keys": {"p256dh": "public", "auth": "auth"},
    }


def test_uses_secret_provider_vapid_claims_ttl_and_timeout():
    calls = []
    sender = PyWebPushSender(
        lambda: "A" * 48,
        subject="mailto:push-ops@example.com",
        timeout_seconds=8,
        webpush_function=lambda **kwargs: calls.append(kwargs) or "accepted",
    )
    result = sender(
        _subscription(),
        '{"notification_id":"n-1"}',
        ttl_seconds=120,
        idempotency_key="idem-1",
    )
    assert result == "accepted"
    assert calls[0]["vapid_claims"] == {"sub": "mailto:push-ops@example.com"}
    assert calls[0]["ttl"] == 120
    assert calls[0]["timeout"] == 8
    assert calls[0]["verbose"] is False
    assert calls[0]["vapid_private_key"] == "A" * 48


def test_rejects_missing_key_without_exposing_secret():
    sender = PyWebPushSender(lambda: "", subject="mailto:ops@example.com", webpush_function=lambda **kwargs: None)
    with pytest.raises(VapidConfigurationError, match="unavailable"):
        sender(_subscription(), "{}", ttl_seconds=30, idempotency_key="id")


def test_rejects_pem_text_and_file_path_as_private_key_source():
    sender = PyWebPushSender(lambda: "/etc/secrets/vapid.pem", subject="mailto:ops@example.com", webpush_function=lambda **kwargs: None)
    with pytest.raises(VapidConfigurationError, match="base64-encoded DER"):
        sender(_subscription(), "{}", ttl_seconds=30, idempotency_key="id")
    pem_sender = PyWebPushSender(
        lambda: "-----BEGIN PRIVATE KEY-----",
        subject="mailto:ops@example.com",
        webpush_function=lambda **kwargs: None,
    )
    with pytest.raises(VapidConfigurationError, match="base64-encoded DER"):
        pem_sender(_subscription(), "{}", ttl_seconds=30, idempotency_key="id")


def test_validates_subject_ttl_and_endpoint():
    with pytest.raises(ValueError, match="mailto"):
        PyWebPushSender(lambda: "key", subject="ops@example.com")
    sender = PyWebPushSender(lambda: "A" * 48, subject="mailto:ops@example.com", webpush_function=lambda **kwargs: None)
    with pytest.raises(ValueError, match="TTL"):
        sender(_subscription(), "{}", ttl_seconds=-1, idempotency_key="id")
    bad = dict(_subscription(), endpoint="http://example.com/push")
    with pytest.raises(ValueError, match="HTTPS"):
        sender(bad, "{}", ttl_seconds=30, idempotency_key="id")



def test_rejects_non_finite_timeout():
    with pytest.raises(ValueError, match="finite"):
        PyWebPushSender(lambda: "A" * 48, subject="mailto:ops@example.com", timeout_seconds=float("nan"))



def test_factory_requires_injected_durable_encrypted_store():
    from integration.pywebpush_sender import build_tenant_web_push_sink
    from integration.tenant_web_push_notification_sink import TenantWebPushNotificationSink

    class Store:
        production_durable = True
        encrypted_at_rest = True

        def list_for_owner(self, context):
            return []

        def delete_for_owner(self, context, device_id):
            return True

    sink = build_tenant_web_push_sink(
        Store(),
        lambda: "A" * 48,
        subject="mailto:ops@example.com",
    )
    assert isinstance(sink, TenantWebPushNotificationSink)
    assert sink.ttl_seconds == 300
