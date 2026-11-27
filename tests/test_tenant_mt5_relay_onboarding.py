from datetime import datetime, timedelta, timezone
from uuid import uuid4

from integration.tenant_mt5_relay_onboarding import (
    TenantMT5RelayOnboardingService,
    TenantMT5RelayTokenVault,
)
from integration.tenant_mt5_relay_registry import TenantMT5RelayRegistry
from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry
from data.feed import MarketDataRequest
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


def test_onboarding_issues_one_time_token_and_stores_only_hash(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantMT5RelayTokenVault(tmp_path / "tokens.sqlite3", connections)
    service = TenantMT5RelayOnboardingService(connections, vault)

    provisioned = service.provision(owner, account_alias="MT5 principal")

    assert provisioned["status"] == "PENDING"
    assert provisioned["token_reveal"] == "ONE_TIME"
    assert len(provisioned["relay_token"]) >= 40
    assert vault.resolve(provisioned["relay_token"]) == (owner, provisioned["connection_id"])
    assert vault.source_id(owner, provisioned["connection_id"]) == provisioned["source_id"]
    with vault._connect() as db:
        row = db.execute("SELECT token_hash FROM tenant_mt5_relay_tokens").fetchone()
    assert row["token_hash"] != provisioned["relay_token"]
    assert len(row["token_hash"]) == 64


def test_first_valid_demo_batch_completes_relay_handshake_and_disconnect_revokes(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantMT5RelayTokenVault(tmp_path / "tokens.sqlite3", connections)
    provisioned = TenantMT5RelayOnboardingService(connections, vault).provision(
        owner, account_alias="MT5 principal"
    )
    sessions = TenantMarketDataSessionRegistry(connections)
    registry = TenantMT5RelayRegistry(
        connections, tmp_path / "relays", vault.source_id, sessions=sessions
    )
    now = datetime.now(timezone.utc)
    payload = {
        "source_id": provisioned["source_id"],
        "account_reference": "mt5_" + "a" * 32,
        "message_id": str(uuid4()),
        "sent_at": now.isoformat(),
        "account_mode": "DEMO",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "candles": [{
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 10,
        }],
    }

    registry.ingest(owner, provisioned["connection_id"], payload)

    account = next(item for item in connections.list_connections(owner)
                   if item["connection_id"] == provisioned["connection_id"])
    assert account["status"] == "CONNECTED"
    assert account["account_reference"] == "mt5_" + "a" * 32
    assert registry.status(owner, provisioned["connection_id"])["connected"] is True
    session = sessions.get(owner, connection_id=provisioned["connection_id"])
    assert session is not None
    assert session.provider_id == "mt5_relay"
    assert len(session.adapter.fetch(MarketDataRequest("EURUSD", "M5", 10))) == 1
    assert vault.revoke(owner, provisioned["connection_id"]) is True
    assert vault.resolve(provisioned["relay_token"]) is None


def test_pending_relay_rejects_non_demo_first_heartbeat(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connections = TenantProviderConnectionRegistry(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    vault = TenantMT5RelayTokenVault(tmp_path / "tokens.sqlite3", connections)
    provisioned = TenantMT5RelayOnboardingService(connections, vault).provision(
        owner, account_alias="MT5 principal"
    )
    registry = TenantMT5RelayRegistry(connections, tmp_path / "relays", vault.source_id)
    now = datetime.now(timezone.utc)
    payload = {
        "source_id": provisioned["source_id"], "account_reference": "mt5_" + "b" * 32,
        "message_id": str(uuid4()),
        "sent_at": now.isoformat(), "account_mode": "REAL",
        "symbol": "EURUSD", "timeframe": "M5",
        "candles": [{
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 10,
        }],
    }

    try:
        registry.ingest(owner, provisioned["connection_id"], payload)
    except ValueError as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("REAL payload must be rejected")
    account = next(item for item in connections.list_connections(owner)
                   if item["connection_id"] == provisioned["connection_id"])
    assert account["status"] == "PENDING"
