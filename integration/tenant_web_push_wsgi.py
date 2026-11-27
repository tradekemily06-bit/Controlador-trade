from __future__ import annotations

import json
import re
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from security.push_subscription_registry import PushSubscriptionInput
from security.tenant_context import TenantContext
from security.tenant_storage import require_tenant_context


_MAX_PUSH_BODY = 8192
_DEVICE_PATH = re.compile(r"^/api/push/subscriptions/([A-Za-z0-9._:-]{1,128})$")


class TenantPushSubscriptionWSGI:
    """Mountable same-origin WSGI routes for tenant-owned push subscriptions.

    Authentication is delegated to the host's trusted identity middleware.
    This module deliberately does not parse caller-supplied tenant IDs or trust
    arbitrary identity headers. Mutation authorization (including CSRF checks
    where cookie sessions are used) is a separate mandatory host callback.
    """

    def __init__(
        self,
        registry,
        *,
        context_resolver: Callable[[dict[str, Any]], TenantContext | None],
        mutation_authorizer: Callable[[dict[str, Any]], bool],
    ) -> None:
        if registry is None:
            raise ValueError("push subscription registry is required")
        if not callable(context_resolver) or not callable(mutation_authorizer):
            raise ValueError("trusted context and mutation authorization callbacks are required")
        self.registry = registry
        self.context_resolver = context_resolver
        self.mutation_authorizer = mutation_authorizer

    @staticmethod
    def _response(start_response, status: HTTPStatus, payload: dict[str, Any]):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        start_response(f"{status.value} {status.phrase}", headers)
        return [body]

    @staticmethod
    def _body(environ: dict[str, Any]) -> dict[str, Any]:
        raw_length = environ.get("CONTENT_LENGTH") or "0"
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise ValueError("content length is invalid") from exc
        if length < 0 or length > _MAX_PUSH_BODY:
            raise ValueError("push subscription payload exceeds the allowed limit")
        raw = environ.get("wsgi.input").read(length)
        if len(raw) != length:
            raise ValueError("push subscription payload is incomplete")
        payload = json.loads(raw or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        return payload

    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = urlsplit(str(environ.get("PATH_INFO", "/"))).path
        if path not in {"/api/push/subscriptions"} and not _DEVICE_PATH.fullmatch(path):
            return None
        if method not in {"GET", "POST", "DELETE"}:
            return self._response(start_response, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

        try:
            context = self.context_resolver(environ)
            owner = require_tenant_context(context)
        except Exception:
            return self._response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "authenticated tenant identity required"})

        if method in {"POST", "DELETE"}:
            try:
                authorized = self.mutation_authorizer(environ) is True
            except Exception:
                authorized = False
            if not authorized:
                return self._response(start_response, HTTPStatus.FORBIDDEN, {"error": "subscription mutation not authorized"})

        try:
            if path == "/api/push/subscriptions":
                if method == "GET":
                    return self._response(start_response, HTTPStatus.OK, {
                        "devices": self.registry.list_devices(owner),
                        "scope": "TENANT_AND_SUBJECT",
                    })
                if method == "POST":
                    payload = self._body(environ)
                    device_id = payload.get("device_id")
                    subscription = payload.get("subscription")
                    if not isinstance(subscription, dict):
                        raise ValueError("subscription must be an object")
                    if set(subscription) - {"endpoint", "keys", "expirationTime"}:
                        raise ValueError("subscription contains unsupported fields")
                    keys = subscription.get("keys")
                    if not isinstance(keys, dict) or set(keys) != {"p256dh", "auth"}:
                        raise ValueError("subscription keys must contain p256dh and auth")
                    result = self.registry.register(
                        owner,
                        device_id,
                        PushSubscriptionInput(
                            endpoint=subscription.get("endpoint"),
                            p256dh=keys.get("p256dh"),
                            auth=keys.get("auth"),
                            expiration_time=subscription.get("expirationTime"),
                        ),
                    )
                    return self._response(start_response, HTTPStatus.CREATED, {"device": result})
            match = _DEVICE_PATH.fullmatch(path)
            if match and method == "DELETE":
                device_id = unquote(match.group(1))
                result = self.registry.revoke(owner, device_id)
                return self._response(start_response, HTTPStatus.OK, {"device": result})
            return self._response(start_response, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._response(start_response, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            # Keep cryptographic/storage/provider internals out of HTTP responses.
            return self._response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "push subscription service unavailable"})
