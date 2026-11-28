from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ALLOWED_PUSH_HOSTS = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)


def _is_allowed_push_host(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    # Providers use a small set of documented host patterns: FCM and Apple
    # use fixed hosts; Mozilla uses one regional/cluster label; WNS uses
    # numbered service hosts. Never accept arbitrary nested subdomains.
    if normalized in {"fcm.googleapis.com", "web.push.apple.com"}:
        return True
    labels = normalized.split(".")
    if normalized == "updates.push.services.mozilla.com":
        return True
    if len(labels) == 4 and labels[1:] == ["notify", "windows", "com"]:
        return bool(re.fullmatch(r"wns[0-9]+", labels[0]))
    return False


class EncryptedPushSubscriptionStore(Protocol):
    """Deployment adapter; implementations must encrypt subscription secrets."""

    production_durable: bool
    encrypted_at_rest: bool

    def list_for_owner(self, context: TenantContext) -> list[dict[str, Any]]:
        ...

    def put_for_owner(
        self, context: TenantContext, device_id: str, record: dict[str, Any]
    ) -> None:
        ...

    def delete_for_owner(self, context: TenantContext, device_id: str) -> bool:
        ...


@dataclass(frozen=True)
class PushSubscriptionInput:
    endpoint: str
    p256dh: str
    auth: str
    expiration_time: int | None = None


def _decode_base64url(value: str, field: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"{field} is invalid")
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError(f"{field} must be base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError(f"{field} is invalid") from exc
    return decoded


def _validate_endpoint(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("endpoint is invalid")
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    try:
        # Reject malformed ports and IP literals before any sender can make a request.
        port = parsed.port
        is_ip_literal = False
        import ipaddress
        try:
            ipaddress.ip_address(hostname)
            is_ip_literal = True
        except ValueError:
            pass
    except ValueError as exc:
        raise ValueError("endpoint host or port is invalid") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or is_ip_literal
        or port not in (None, 443)
        or not _is_allowed_push_host(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("endpoint must use an approved HTTPS browser push service without credentials or fragment")
    return value


class TenantPushSubscriptionRegistry:
    """Tenant-scoped lifecycle for encrypted, per-device Web Push subscriptions.

    Device IDs are owner-local record keys, never authentication credentials.
    Sender, VAPID and WSGI route components live in separate integration
    modules. This registry does not configure or activate them. A deployment
    must inject a durable encrypted store before registration or revocation
    can be enabled.
    """

    def __init__(self, store: EncryptedPushSubscriptionStore) -> None:
        if store is None:
            raise ValueError("an encrypted subscription store is required")
        if getattr(store, "production_durable", False) is not True:
            raise RuntimeError("production-durable push subscription storage is required")
        if getattr(store, "encrypted_at_rest", False) is not True:
            raise RuntimeError("encrypted-at-rest push subscription storage is required")
        for method in ("list_for_owner", "put_for_owner", "delete_for_owner"):
            if not callable(getattr(store, method, None)):
                raise ValueError(f"push subscription store must implement {method}")
        self.store = store

    def register(
        self,
        context: TenantContext | None,
        device_id: str,
        subscription: PushSubscriptionInput,
    ) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id must be an opaque 1-128 character record key")
        if not isinstance(subscription, PushSubscriptionInput):
            raise ValueError("subscription must be PushSubscriptionInput")
        endpoint = _validate_endpoint(subscription.endpoint)
        public_key = _decode_base64url(subscription.p256dh, "p256dh")
        auth_secret = _decode_base64url(subscription.auth, "auth")
        if len(public_key) != 65 or public_key[0] != 4:
            raise ValueError("p256dh must be an uncompressed 65-byte P-256 public key")
        if len(auth_secret) != 16:
            raise ValueError("auth must decode to exactly 16 bytes")
        expiration = subscription.expiration_time
        if expiration is not None and (
            isinstance(expiration, bool) or not isinstance(expiration, int) or expiration <= 0
        ):
            raise ValueError("expiration_time must be a positive Unix timestamp or null")

        # Re-registering the same owner-local device key rotates its endpoint/keys.
        self.store.put_for_owner(
            owner,
            device_id,
            {
                "endpoint": endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                "expiration_time": expiration,
                "status": "ACTIVE",
            },
        )
        return {"device_id": device_id, "status": "ACTIVE", "scope": "TENANT_AND_SUBJECT"}

    def list_devices(self, context: TenantContext | None) -> list[dict[str, Any]]:
        owner = require_tenant_context(context)
        # Never return endpoint URLs or encryption keys to the browser.
        return [
            {
                "device_id": str(item.get("device_id", "")),
                "status": str(item.get("status", "ACTIVE")),
                "expiration_time": item.get("expiration_time"),
            }
            for item in self.store.list_for_owner(owner)
        ]

    def revoke(self, context: TenantContext | None, device_id: str) -> dict[str, Any]:
        owner = require_tenant_context(context)
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id must be an opaque 1-128 character record key")
        revoked = bool(self.store.delete_for_owner(owner, device_id))
        return {
            "device_id": device_id,
            "revoked": revoked,
            "scope": "TENANT_AND_SUBJECT",
        }

    def revoke_expired_endpoint(
        self, context: TenantContext | None, device_id: str, *, http_status: int
    ) -> dict[str, Any]:
        """Remove only an owner's subscription after a sender confirms 404/410."""
        if http_status not in {404, 410}:
            raise ValueError("only confirmed 404/410 push responses may expire a subscription")
        return self.revoke(context, device_id)
