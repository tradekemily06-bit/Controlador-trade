from __future__ import annotations

import io
import json
from uuid import uuid4

from standalone_app import StandaloneWSGIApplication
from security.tenant_context import TenantContext


CONNECTION_ID = "a" * 32


class TokenResolver:
    def __init__(self, result):
        self.result = result
        self.seen = []

    def resolve(self, token):
        self.seen.append(token)
        return self.result


class RelayRegistry:
    def __init__(self):
        self.calls = []

    def ingest(self, context, connection_id, payload):
        self.calls.append((context, connection_id, payload))
        return {"accepted": 1, "symbol": "EURUSD", "timeframe": "M5"}


class Runtime:
    closed = False


def request(app, connection_id=CONNECTION_ID, *, scheme="https", token="relay-token", body=None):
    payload = json.dumps(body or {"symbol": "EURUSD"}).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": f"/api/bridge/mt5/connections/{connection_id}/candles",
        "QUERY_STRING": "",
        "REMOTE_ADDR": "198.51.100.10",
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
        "wsgi.url_scheme": scheme,
        "HTTP_AUTHORIZATION": f"Bearer {token}",
    }
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response))
    return captured["status"], json.loads(response.decode())


def test_tenant_mt5_relay_route_uses_server_resolved_owner_and_account():
    owner = TenantContext("tenant-one", "subject-one")
    resolver = TokenResolver((owner, CONNECTION_ID))
    registry = RelayRegistry()
    runtime = Runtime()
    runtime.tenant_mt5_relay_token_resolver = resolver
    runtime.tenant_mt5_relay_registry = registry

    status, body = request(
        StandaloneWSGIApplication(runtime),
        body={"symbol": "EURUSD", "tenant_id": "attacker-tenant", "connection_id": "attacker-account"},
    )

    assert status == "202 Accepted"
    assert body["read_only"] is True
    assert body["execution_authorized"] is False
    assert resolver.seen == ["relay-token"]
    assert registry.calls[0][0] == owner
    assert registry.calls[0][1] == CONNECTION_ID
    assert registry.calls[0][2]["tenant_id"] == "attacker-tenant"


def test_tenant_mt5_relay_route_rejects_token_for_another_account():
    owner = TenantContext("tenant-one", "subject-one")
    resolver = TokenResolver((owner, "b" * 32))
    registry = RelayRegistry()
    runtime = Runtime()
    runtime.tenant_mt5_relay_token_resolver = resolver
    runtime.tenant_mt5_relay_registry = registry

    status, body = request(StandaloneWSGIApplication(runtime))

    assert status == "403 Forbidden"
    assert "não pertence" in body["error"]
    assert registry.calls == []


def test_tenant_mt5_relay_route_requires_tls():
    owner = TenantContext("tenant-one", "subject-one")
    resolver = TokenResolver((owner, CONNECTION_ID))
    registry = RelayRegistry()
    runtime = Runtime()
    runtime.tenant_mt5_relay_token_resolver = resolver
    runtime.tenant_mt5_relay_registry = registry

    status, body = request(StandaloneWSGIApplication(runtime), scheme="http")

    assert status == "401 Unauthorized"
    assert resolver.seen == []
    assert registry.calls == []


def test_tenant_mt5_relay_route_fails_closed_without_server_provisioning():
    owner = TenantContext("tenant-one", "subject-one")
    runtime = Runtime()
    runtime.tenant_mt5_relay_token_resolver = TokenResolver((owner, CONNECTION_ID))
    runtime.tenant_mt5_relay_registry = None

    status, body = request(StandaloneWSGIApplication(runtime))

    assert status == "503 Service Unavailable"
    assert "não provisionado" in body["error"]
