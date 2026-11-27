from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from integration.tenant_tradingview_alert_inbox import (
    TenantTradingViewAlertInbox,
    TradingViewAlertError,
)
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


SECRET = "tradingview-webhook-secret-with-at-least-32-bytes"


def _account(registry, owner):
    return registry.record_verified_connection(
        owner, provider_id="tradingview_webhook", account_alias="TV alertas",
        account_reference="tv-webhook-1", capabilities=["alerts:receive"],
        adapter_verified=True,
    )


def _payload(**overrides):
    payload = {
        "secret": SECRET,
        "event_id": uuid4().hex,
        "ticker": "NASDAQ:AAPL",
        "interval": "5",
        "action": "BUY",
        "price": 231.45,
        "fired_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    return payload


def _setup(tmp_path):
    connections = TenantProviderConnectionRegistry(
        SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    )
    owner = TenantContext("tenant-a", "alice")
    account = _account(connections, owner)
    inbox = TenantTradingViewAlertInbox(
        tmp_path / "alerts.sqlite3", connections,
        secret_resolver=lambda context, connection_id: SECRET,
    )
    return connections, owner, account, inbox


def test_valid_alert_is_stored_without_secret_and_never_authorizes_execution(tmp_path):
    _, owner, account, inbox = _setup(tmp_path)
    payload = _payload()

    result = inbox.ingest(owner, account["connection_id"], payload)
    events = inbox.list_events(owner, account["connection_id"])

    assert result["accepted"] is True
    assert result["read_only"] is True
    assert result["execution_authorized"] is False
    assert len(events) == 1
    assert SECRET not in str(events)


def test_alert_rejects_wrong_secret_and_expired_event(tmp_path):
    _, owner, account, inbox = _setup(tmp_path)
    with pytest.raises(PermissionError, match="segredo"):
        inbox.ingest(owner, account["connection_id"], _payload(secret="wrong"))
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    with pytest.raises(TradingViewAlertError, match="fired_at"):
        inbox.ingest(owner, account["connection_id"], _payload(fired_at=old.isoformat()))


def test_alert_event_id_is_idempotent_per_connection(tmp_path):
    _, owner, account, inbox = _setup(tmp_path)
    payload = _payload()
    inbox.ingest(owner, account["connection_id"], payload)
    with pytest.raises(TradingViewAlertError, match="repetido"):
        inbox.ingest(owner, account["connection_id"], payload)


def test_alerts_are_isolated_by_tenant_identity(tmp_path):
    _, owner, account, inbox = _setup(tmp_path)
    other = TenantContext("tenant-b", "bob")
    inbox.ingest(owner, account["connection_id"], _payload())
    assert inbox.list_events(other, account["connection_id"]) == []
    with pytest.raises(PermissionError, match="não pertence"):
        inbox.ingest(other, account["connection_id"], _payload())


@pytest.mark.parametrize("bad_price", [
    True,
    "231.45",
    float("nan"),
    float("inf"),
    float("-inf"),
    10 ** 1000,
])
def test_alert_rejects_non_finite_or_non_numeric_price(tmp_path, bad_price):
    _, owner, account, inbox = _setup(tmp_path)

    with pytest.raises(TradingViewAlertError, match="price"):
        inbox.ingest(owner, account["connection_id"], _payload(price=bad_price))

    assert inbox.list_events(owner, account["connection_id"]) == []
