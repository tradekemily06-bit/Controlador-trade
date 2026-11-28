import pytest
from datetime import datetime, timedelta, timezone

from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry
from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry


class FakeAdapter:
    def fetch(self, request):
        return []


def _setup(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    return connections, TenantMarketDataSessionRegistry(connections)


def _verified(connections, owner, alias, reference):
    return connections.record_verified_connection(
        owner, provider_id="broker_x", account_alias=alias,
        account_reference=reference, capabilities=["candles:read"],
        adapter_verified=True,
    )


def test_two_accounts_of_same_provider_bind_independent_adapters(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    one = _verified(connections, owner, "Conta A", "account-a")
    two = _verified(connections, owner, "Conta B", "account-b")
    adapter_a, adapter_b = FakeAdapter(), FakeAdapter()
    sessions.bind(owner, connection_id=one["connection_id"], adapter=adapter_a, source="broker_x:account-a", handshake_verified=True)
    sessions.bind(owner, connection_id=two["connection_id"], adapter=adapter_b, source="broker_x:account-b", handshake_verified=True)
    assert sessions.get(owner, connection_id=one["connection_id"]).adapter is adapter_a
    assert sessions.get(owner, connection_id=two["connection_id"]).adapter is adapter_b
    assert [item["adapter_status"] for item in sessions.status(owner)] == ["BOUND", "BOUND"]


def test_session_isolation_between_tenants_and_subjects(tmp_path):
    connections, sessions = _setup(tmp_path)
    alice, bob = TenantContext("tenant-a", "alice"), TenantContext("tenant-b", "bob")
    account = _verified(connections, alice, "Conta A", "account-a")
    sessions.bind(alice, connection_id=account["connection_id"], adapter=FakeAdapter(), source="broker_x", handshake_verified=True)
    assert sessions.get(bob, connection_id=account["connection_id"]) is None
    assert sessions.status(bob) == []
    assert sessions.unbind(bob, connection_id=account["connection_id"]) is False
    assert sessions.get(alice, connection_id=account["connection_id"]) is not None


def test_binding_requires_verified_handshake_and_owned_connection(tmp_path):
    connections, sessions = _setup(tmp_path)
    alice, bob = TenantContext("tenant-a", "alice"), TenantContext("tenant-b", "bob")
    account = _verified(connections, alice, "Conta A", "account-a")
    with pytest.raises(PermissionError, match="verified provider handshake"):
        sessions.bind(alice, connection_id=account["connection_id"], adapter=FakeAdapter(), source="broker_x", handshake_verified=False)
    with pytest.raises(PermissionError, match="does not belong"):
        sessions.bind(bob, connection_id=account["connection_id"], adapter=FakeAdapter(), source="broker_x", handshake_verified=True)


def test_one_adapter_instance_cannot_be_reused_for_two_accounts(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    one = _verified(connections, owner, "Conta A", "account-a")
    two = _verified(connections, owner, "Conta B", "account-b")
    adapter = FakeAdapter()
    sessions.bind(owner, connection_id=one["connection_id"], adapter=adapter, source="broker_x:account-a", handshake_verified=True)
    with pytest.raises(ValueError, match="cannot be shared"):
        sessions.bind(owner, connection_id=two["connection_id"], adapter=adapter, source="broker_x:account-b", handshake_verified=True)


def test_disconnected_account_cannot_bind_adapter(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    account = _verified(connections, owner, "Conta A", "account-a")
    connections.mark_disconnected(owner, connection_id=account["connection_id"])
    with pytest.raises(PermissionError, match="fresh handshake"):
        sessions.bind(owner, connection_id=account["connection_id"], adapter=FakeAdapter(), source="broker_x", handshake_verified=True)


def test_adapter_health_is_reported_without_exposing_unapproved_fields(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    account = _verified(connections, owner, "Conta A", "account-a")

    class HealthAdapter(FakeAdapter):
        def status(self):
            return {
                "connected": True,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "source_id": "safe-source",
                "stored_candles": 12,
                "api_key": "must-not-leak",
            }

    sessions.bind(
        owner, connection_id=account["connection_id"], adapter=HealthAdapter(),
        source="broker_x:account-a", handshake_verified=True,
    )
    status = sessions.status(owner)[0]
    assert status["adapter_status"] == "BOUND"
    assert status["health_status"] == "CONNECTED"
    assert status["health"]["stored_candles"] == 12
    assert "api_key" not in status["health"]


def test_stale_adapter_heartbeat_is_not_reported_as_connected(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    account = _verified(connections, owner, "Conta A", "account-a")

    class StaleAdapter(FakeAdapter):
        def status(self):
            return {
                "connected": True,
                "last_seen": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
            }

    sessions.bind(
        owner, connection_id=account["connection_id"], adapter=StaleAdapter(),
        source="broker_x:account-a", handshake_verified=True,
    )
    status = sessions.status(owner)[0]
    assert status["adapter_status"] == "BOUND"
    assert status["health_status"] == "HEARTBEAT_STALE_OR_UNVERIFIED"



def test_quote_stream_backpressure_is_not_reported_as_healthy(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    account = _verified(connections, owner, "Conta A", "account-a")

    class BackpressuredAdapter(FakeAdapter):
        def status(self):
            return {
                "connected": True,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "active_spot_symbols": 2,
                "spot_event_queue_depth": 2048,
                "spot_event_overflow_count": 3,
                "last_spot_overflow_at": datetime.now(timezone.utc).isoformat(),
            }

    sessions.bind(
        owner, connection_id=account["connection_id"], adapter=BackpressuredAdapter(),
        source="ctrader_open_api:account-a", handshake_verified=True,
    )
    status = sessions.status(owner)[0]
    assert status["health_status"] == "STREAM_BACKPRESSURE"
    assert status["health"]["spot_event_overflow_count"] == 3



def test_old_quote_queue_overflow_does_not_keep_connection_degraded(tmp_path):
    connections, sessions = _setup(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    account = _verified(connections, owner, "Conta A", "account-a")

    class RecoveredAdapter(FakeAdapter):
        def status(self):
            return {
                "connected": True,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "spot_event_overflow_count": 3,
                "last_spot_overflow_at": "2020-01-01T00:00:00+00:00",
            }

    sessions.bind(
        owner, connection_id=account["connection_id"], adapter=RecoveredAdapter(),
        source="ctrader_open_api:account-a", handshake_verified=True,
    )
    status = sessions.status(owner)[0]
    assert status["health_status"] == "CONNECTED"


def test_process_restart_discards_adapter_binding_without_falsely_claiming_connected(tmp_path):
    database = tmp_path / "tenant-session-restart.sqlite3"
    owner = TenantContext("tenant-restart", "alice")
    first_storage = SQLiteTenantStorage(database)
    first_connections = TenantProviderConnectionRegistry(first_storage)
    first_sessions = TenantMarketDataSessionRegistry(first_connections)
    account = _verified(first_connections, owner, "Conta A", "account-a")
    first_sessions.bind(
        owner, connection_id=account["connection_id"], adapter=FakeAdapter(),
        source="broker_x:account-a", handshake_verified=True,
    )
    assert first_sessions.status(owner)[0]["adapter_status"] == "BOUND"

    # A new process reconstructs durable metadata but not the old Python adapter.
    restarted_storage = SQLiteTenantStorage(database)
    restarted_connections = TenantProviderConnectionRegistry(restarted_storage)
    restarted_sessions = TenantMarketDataSessionRegistry(restarted_connections)
    status = restarted_sessions.status(owner)[0]

    assert status["status"] == "CONNECTED"  # durable metadata only
    assert status["adapter_status"] == "NOT_BOUND"
    assert status["health_status"] == "NOT_BOUND"
    assert restarted_sessions.get(owner, connection_id=account["connection_id"]) is None



def test_adapter_instance_cannot_cross_tenant_boundary(tmp_path):
    connections, sessions = _setup(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-b", "bob")
    account_a = _verified(connections, alice, "Conta A", "account-a")
    account_b = _verified(connections, bob, "Conta B", "account-b")
    shared_adapter = FakeAdapter()

    sessions.bind(
        alice, connection_id=account_a["connection_id"], adapter=shared_adapter,
        source="broker_x:account-a", handshake_verified=True,
    )

    with pytest.raises(ValueError, match="cannot be shared"):
        sessions.bind(
            bob, connection_id=account_b["connection_id"], adapter=shared_adapter,
            source="broker_x:account-b", handshake_verified=True,
        )

    assert sessions.get(alice, connection_id=account_a["connection_id"]).adapter is shared_adapter
    assert sessions.get(bob, connection_id=account_b["connection_id"]) is None
