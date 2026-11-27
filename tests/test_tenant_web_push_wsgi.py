import base64
import io
import json

from integration.tenant_web_push_wsgi import TenantPushSubscriptionWSGI
from security.push_subscription_registry import TenantPushSubscriptionRegistry
from security.tenant_context import TenantContext


class Store:
    production_durable = True
    encrypted_at_rest = True

    def __init__(self):
        self.rows = {}

    def list_for_owner(self, context):
        return [
            {**value, "device_id": key}
            for (tenant, subject, key), value in self.rows.items()
            if tenant == context.tenant_id and subject == context.subject_id
        ]

    def put_for_owner(self, context, device_id, record):
        self.rows[(context.tenant_id, context.subject_id, device_id)] = record

    def delete_for_owner(self, context, device_id):
        return self.rows.pop((context.tenant_id, context.subject_id, device_id), None) is not None


def request(app, path, method="GET", payload=None, context=None, mutation=True):
    body = json.dumps(payload).encode() if payload is not None else b""
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    app.context_resolver = lambda _: context
    app.mutation_authorizer = lambda _: mutation
    response = app(environ, start_response)
    return captured, b"".join(response or [])


def _valid_subscription():
    public_key = b"\x04" + b"p" * 64
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/example",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
            "auth": base64.urlsafe_b64encode(b"a" * 16).decode().rstrip("="),
        },
        "expirationTime": None,
    }


def test_routes_require_trusted_context_and_mutation_authorization():
    app = TenantPushSubscriptionWSGI(
        TenantPushSubscriptionRegistry(Store()),
        context_resolver=lambda _: None,
        mutation_authorizer=lambda _: True,
    )
    captured, _ = request(app, "/api/push/subscriptions")
    assert captured["status"] == "401 Unauthorized"

    captured, _ = request(
        app,
        "/api/push/subscriptions",
        method="POST",
        payload={"device_id": "browser-1", "subscription": _valid_subscription()},
        context=TenantContext("tenant-a", "alice"),
        mutation=False,
    )
    assert captured["status"] == "403 Forbidden"


def test_register_list_and_revoke_are_owner_scoped():
    app = TenantPushSubscriptionWSGI(
        TenantPushSubscriptionRegistry(Store()),
        context_resolver=lambda _: TenantContext("tenant-a", "alice"),
        mutation_authorizer=lambda _: True,
    )
    captured, body = request(
        app,
        "/api/push/subscriptions",
        method="POST",
        payload={"device_id": "browser-1", "subscription": _valid_subscription()},
        context=TenantContext("tenant-a", "alice"),
    )
    assert captured["status"] == "201 Created"
    assert json.loads(body)["device"]["status"] == "ACTIVE"

    captured, body = request(
        app,
        "/api/push/subscriptions",
        context=TenantContext("tenant-a", "bob"),
    )
    assert captured["status"] == "200 OK"
    assert json.loads(body)["devices"] == []

    captured, body = request(
        app,
        "/api/push/subscriptions/browser-1",
        method="DELETE",
        context=TenantContext("tenant-a", "alice"),
    )
    assert captured["status"] == "200 OK"
    assert json.loads(body)["device"]["revoked"] is True


def test_rejects_bad_payload_and_unknown_route_falls_through():
    app = TenantPushSubscriptionWSGI(
        TenantPushSubscriptionRegistry(Store()),
        context_resolver=lambda _: TenantContext("tenant-a", "alice"),
        mutation_authorizer=lambda _: True,
    )
    captured, _ = request(
        app,
        "/api/push/subscriptions",
        method="POST",
        payload={"device_id": "../bad", "subscription": _valid_subscription()},
        context=TenantContext("tenant-a", "alice"),
    )
    assert captured["status"] == "400 Bad Request"
    assert app({"PATH_INFO": "/api/other", "REQUEST_METHOD": "GET"}, lambda *_: None) is None
