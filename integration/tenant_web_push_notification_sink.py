from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from security.push_subscription_registry import (
    EncryptedPushSubscriptionStore,
    _validate_endpoint,
)
from security.tenant_context import TenantContext


_MAX_PUSH_PAYLOAD_BYTES = 3500
_PUBLIC_FIELDS = (
    "notification_id",
    "title",
    "message",
    "kind",
    "severity",
    "requires_attention",
    "blocking",
    "created_at",
    "symbol",
    "timeframe",
    "signal",
)


class WebPushDeliveryError(RuntimeError):
    """A generic delivery failure that deliberately excludes provider details."""


class NoActivePushSubscriptions(WebPushDeliveryError):
    """The addressed owner has no active device to receive this event."""


class TenantWebPushNotificationSink:
    """Deliver one explicitly addressed event to that owner's active devices.

    The sender callback is the narrow provider boundary. A deployment can wrap
    pywebpush (or another standards-compliant Web Push implementation) without
    giving this class VAPID private-key access or allowing it to choose
    recipients. Subscription storage must be durable and encrypted at rest.
    """

    def __init__(
        self,
        store: EncryptedPushSubscriptionStore,
        sender: Callable[..., Any],
        *,
        ttl_seconds: int = 300,
    ) -> None:
        if store is None:
            raise ValueError("an encrypted push subscription store is required")
        if getattr(store, "production_durable", False) is not True:
            raise RuntimeError("production-durable push subscription storage is required")
        if getattr(store, "encrypted_at_rest", False) is not True:
            raise RuntimeError("encrypted-at-rest push subscription storage is required")
        if not callable(getattr(store, "list_for_owner", None)):
            raise ValueError("push subscription store must implement list_for_owner")
        if not callable(getattr(store, "delete_for_owner", None)):
            raise ValueError("push subscription store must implement delete_for_owner")
        if not callable(sender):
            raise ValueError("a Web Push sender callback is required")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 0 <= ttl_seconds <= 2419200:
            raise ValueError("ttl_seconds must be an integer between 0 and 2419200")
        self.store = store
        self.sender = sender
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _public_payload(payload: Mapping[str, Any], idempotency_key: str) -> str:
        if not isinstance(payload, Mapping):
            raise ValueError("notification payload must be an object")
        safe = {key: payload[key] for key in _PUBLIC_FIELDS if key in payload}
        if not isinstance(safe.get("notification_id"), str) or not safe["notification_id"].strip():
            raise ValueError("notification_id is required for Web Push delivery")
        if not isinstance(safe.get("title"), str) or not safe["title"].strip():
            raise ValueError("notification title is required for Web Push delivery")
        if not isinstance(safe.get("message"), str) or not safe["message"].strip():
            raise ValueError("notification message is required for Web Push delivery")
        safe["idempotency_key"] = idempotency_key
        encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > _MAX_PUSH_PAYLOAD_BYTES:
            raise ValueError("Web Push payload exceeds the 3500-byte safety limit")
        return encoded

    @staticmethod
    def _http_status(error: BaseException) -> int | None:
        direct = getattr(error, "status_code", None)
        if isinstance(direct, int):
            return direct
        response = getattr(error, "response", None)
        nested = getattr(response, "status_code", None)
        return nested if isinstance(nested, int) else None

    def deliver(
        self,
        idempotency_key: str,
        recipient: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> None:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not isinstance(recipient, Mapping):
            raise PermissionError("explicit tenant recipient is required")
        tenant_id = recipient.get("tenant_id")
        subject_id = recipient.get("subject_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise PermissionError("explicit tenant recipient is required")
        if not isinstance(subject_id, str) or not subject_id.strip():
            raise PermissionError("explicit subject recipient is required")

        context = TenantContext(tenant_id, subject_id)
        encoded_payload = self._public_payload(payload, idempotency_key)
        records = self.store.list_for_owner(context)
        if not isinstance(records, list):
            raise WebPushDeliveryError("push subscription store returned an invalid result")

        active = [record for record in records if isinstance(record, dict) and record.get("status") == "ACTIVE"]
        if not active:
            raise NoActivePushSubscriptions("no active push subscriptions for addressed owner")

        failures: list[BaseException] = []
        attempted = 0
        delivered = 0
        for record in active:
            device_id = record.get("device_id")
            endpoint = record.get("endpoint")
            keys = record.get("keys")
            if not isinstance(device_id, str) or not device_id.strip():
                raise WebPushDeliveryError("push subscription record has no device id")
            if not isinstance(keys, dict):
                raise WebPushDeliveryError("push subscription record has invalid keys")
            _validate_endpoint(endpoint)
            subscription_info = {
                "endpoint": endpoint,
                "keys": {"p256dh": keys.get("p256dh"), "auth": keys.get("auth")},
            }
            if not all(isinstance(value, str) and value for value in subscription_info["keys"].values()):
                raise WebPushDeliveryError("push subscription record has invalid keys")
            attempted += 1
            try:
                self.sender(
                    subscription_info,
                    encoded_payload,
                    ttl_seconds=self.ttl_seconds,
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                if self._http_status(exc) in {404, 410}:
                    self.store.delete_for_owner(context, device_id)
                else:
                    failures.append(exc)
            else:
                delivered += 1

        if attempted == 0 or delivered == 0:
            raise NoActivePushSubscriptions("no active push subscription accepted the event")
        if failures:
            raise WebPushDeliveryError(f"Web Push delivery failed for {len(failures)} device(s)")
