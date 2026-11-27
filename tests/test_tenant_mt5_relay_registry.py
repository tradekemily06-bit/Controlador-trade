from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from integration.tenant_mt5_relay_registry import TenantMT5RelayRegistry
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


def _connection(registry, owner, alias):
    return registry.record_pending_connection(
        owner, provider_id="mt5_relay", account_alias=alias,
        account_reference="relay:" + alias, capabilities=["candles:read"],
    )


def _payload(source_id):
    now = datetime.now(timezone.utc)
    account_reference = "mt5_" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:32]
    return {
        "source_id": source_id,
        "account_reference": account_reference,
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


def test_each_verified_account_gets_an_independent_relay_database(tmp_path):
    connections = TenantProviderConnectionRegistry(
        SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    )
    owner = TenantContext("tenant-a", "alice")
    first = _connection(connections, owner, "MT5 principal")
    second = _connection(connections, owner, "MT5 secundária")
    sources = {
        first["connection_id"]: "mt5-account-one",
        second["connection_id"]: "mt5-account-two",
    }
    registry = TenantMT5RelayRegistry(
        connections, tmp_path / "relays",
        source_id_resolver=lambda context, connection_id: sources[connection_id],
    )

    registry.ingest(owner, first["connection_id"], _payload("mt5-account-one"))
    registry.ingest(owner, second["connection_id"], _payload("mt5-account-two"))

    assert registry.status(owner, first["connection_id"])["stored_candles"] == 1
    assert registry.status(owner, second["connection_id"])["stored_candles"] == 1
    assert len(list((tmp_path / "relays").glob("*.sqlite3"))) == 2


def test_relay_payload_cannot_switch_account_source(tmp_path):
    connections = TenantProviderConnectionRegistry(
        SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    )
    owner = TenantContext("tenant-a", "alice")
    account = _connection(connections, owner, "MT5 principal")
    registry = TenantMT5RelayRegistry(
        connections, tmp_path / "relays",
        source_id_resolver=lambda context, connection_id: "server-provisioned-source",
    )

    with pytest.raises(ValueError, match="origem provisionada"):
        registry.ingest(owner, account["connection_id"], _payload("attacker-selected-source"))
    assert registry.status(owner, account["connection_id"])["stored_candles"] == 0


def test_relay_connection_is_not_accessible_to_another_tenant(tmp_path):
    connections = TenantProviderConnectionRegistry(
        SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    )
    owner = TenantContext("tenant-a", "alice")
    other = TenantContext("tenant-b", "bob")
    account = _connection(connections, owner, "MT5 principal")
    registry = TenantMT5RelayRegistry(
        connections, tmp_path / "relays",
        source_id_resolver=lambda context, connection_id: "server-source",
    )

    with pytest.raises(PermissionError, match="não pertence"):
        registry.status(other, account["connection_id"])


def test_relay_connection_binds_first_terminal_reference_and_rejects_account_switch(tmp_path):
    connections = TenantProviderConnectionRegistry(
        SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    )
    owner = TenantContext("tenant-a", "alice")
    account = _connection(connections, owner, "MT5 principal")
    source = "server-provisioned-source"
    registry = TenantMT5RelayRegistry(
        connections, tmp_path / "relays",
        source_id_resolver=lambda context, connection_id: source,
    )
    first = _payload(source)
    registry.ingest(owner, account["connection_id"], first)
    saved = next(item for item in connections.list_connections(owner) if item["connection_id"] == account["connection_id"])
    assert saved["status"] == "CONNECTED"
    assert saved["account_reference"] == first["account_reference"]

    second = _payload(source)
    second["account_reference"] = "mt5_" + "f" * 32
    with pytest.raises(PermissionError, match="não corresponde à conta vinculada"):
        registry.ingest(owner, account["connection_id"], second)
    assert registry.status(owner, account["connection_id"])["stored_candles"] == 1
