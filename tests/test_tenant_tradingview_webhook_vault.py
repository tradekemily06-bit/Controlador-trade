from datetime import datetime, timezone
import io
import json

from standalone_app import StandaloneWSGIApplication
from integration.tenant_tradingview_alert_inbox import TenantTradingViewAlertInbox
from integration.tenant_tradingview_webhook_vault import (
    TenantTradingViewWebhookOnboardingService,
    TenantTradingViewWebhookVault,
)
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


def test_tradingview_secret_is_hashed_and_first_valid_alert_activates_connection(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantTradingViewWebhookVault(tmp_path / "webhooks.sqlite3", connections)
    provisioned = TenantTradingViewWebhookOnboardingService(connections, vault).provision(
        owner, account_alias="TradingView principal"
    )
    inbox = TenantTradingViewAlertInbox(tmp_path / "alerts.sqlite3", connections, vault)
    payload = {
        "secret": provisioned["webhook_secret"],
        "event_id": "event-12345678",
        "ticker": "EURUSD",
        "interval": "5",
        "action": "BUY",
        "fired_at": datetime.now(timezone.utc).isoformat(),
        "price": 1.1234,
    }

    result = inbox.ingest(owner, provisioned["connection_id"], payload)

    assert result["accepted"] is True
    account = next(item for item in connections.list_connections(owner)
                   if item["connection_id"] == provisioned["connection_id"])
    assert account["status"] == "CONNECTED"
    assert inbox.list_events(owner, provisioned["connection_id"])[0]["action"] == "BUY"
    with vault._connect() as db:
        row = db.execute("SELECT secret_hash FROM tenant_tradingview_webhook_secrets").fetchone()
    assert row["secret_hash"] != provisioned["webhook_secret"]
    assert vault.revoke(owner, provisioned["connection_id"]) is True
    assert vault.resolve_secret(provisioned["webhook_secret"]) is None


def test_public_tradingview_webhook_route_resolves_owner_from_secret(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantTradingViewWebhookVault(tmp_path / "webhooks.sqlite3", connections)
    provisioned = TenantTradingViewWebhookOnboardingService(connections, vault).provision(
        owner, account_alias="TradingView principal"
    )
    inbox = TenantTradingViewAlertInbox(tmp_path / "alerts.sqlite3", connections, vault)

    class Runtime:
        closed = False
        tenant_tradingview_webhook_vault = vault
        tenant_tradingview_alert_inbox = inbox

    payload = {
        "secret": provisioned["webhook_secret"],
        "event_id": "event-abcdefgh",
        "ticker": "EURUSD",
        "interval": "5",
        "action": "WAIT",
        "fired_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(payload).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": provisioned["endpoint_path"],
        "QUERY_STRING": "",
        "REMOTE_ADDR": "198.51.100.20",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
        "wsgi.url_scheme": "https",
    }
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status

    response = b"".join(StandaloneWSGIApplication(Runtime())(environ, start_response))
    result = json.loads(response.decode())
    assert captured["status"] == "202 Accepted"
    assert result["accepted"] is True
    assert inbox.list_events(owner, provisioned["connection_id"])[0]["action"] == "WAIT"


def test_tradingview_webhook_route_rejects_http(tmp_path):
    class Runtime:
        closed = False
        tenant_tradingview_webhook_vault = object()
        tenant_tradingview_alert_inbox = object()

    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/webhooks/tradingview/" + ("a" * 32),
        "QUERY_STRING": "",
        "REMOTE_ADDR": "198.51.100.20",
        "CONTENT_LENGTH": "2",
        "wsgi.input": io.BytesIO(b"{}"),
        "wsgi.url_scheme": "http",
    }
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status

    response = b"".join(StandaloneWSGIApplication(Runtime())(environ, start_response))
    result = json.loads(response.decode())
    assert captured["status"] == "401 Unauthorized"
    assert "HTTPS" in result["error"]
