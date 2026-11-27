import pytest

from integration.tenant_market_data_sessions import TenantMarketDataSessionRegistry
from integration.tenant_provider_connection_service import TenantProviderConnectionService
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


class Vault:
    def __init__(self):
        self.calls = []

    def resolve(self, context, reference):
        self.calls.append((context, reference))
        if context.tenant_id != "tenant-a" or reference != "vault://tenant-a/broker-a":
            return None
        return {"api_key": "ephemeral-secret"}


class Adapter:
    def __init__(self, credentials, *, verified=True, provider_id="broker_a"):
        self.received_credentials = credentials
        self.verified = verified
        self.provider_id = provider_id
        self.connected = False
        self.disconnected = False

    def connect(self):
        self.connected = True

    def handshake(self):
        return {
            "provider_id": self.provider_id,
            "account_reference": "account-123",
            "capabilities": ["candles:read"],
            "verified": self.verified,
        }

    def fetch(self, request):
        return []

    def disconnect(self):
        self.disconnected = True


def _service(tmp_path, vault, factory):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    sessions = TenantMarketDataSessionRegistry(connections)
    service = TenantProviderConnectionService(
        connections, sessions, secret_resolver=vault,
        adapter_factories={"broker_a": factory},
    )
    return connections, sessions, service


def test_connection_service_resolves_tenant_secret_and_binds_verified_adapter(tmp_path):
    vault = Vault()
    adapters = []
    def factory(credentials):
        adapter = Adapter(credentials)
        adapters.append(adapter)
        return adapter
    connections, sessions, service = _service(tmp_path, vault, factory)
    owner = TenantContext("tenant-a", "alice")
    result = service.connect(
        owner, provider_id="broker_a", account_alias="Conta principal",
        credential_ref="vault://tenant-a/broker-a",
    )
    assert result["status"] == "CONNECTED"
    assert result["adapter_status"] == "ADAPTER_BOUND"
    assert result["execution_authorized"] is False
    assert sessions.get(owner, connection_id=result["connection_id"]).adapter is adapters[0]
    assert vault.calls == [(owner, "vault://tenant-a/broker-a")]
    assert "ephemeral-secret" not in str(result)
    assert connections.list_connections(owner)[0]["account_reference"] == "account-123"


def test_connection_service_rejects_unverified_provider_handshake(tmp_path):
    vault = Vault()
    adapters = []
    def factory(credentials):
        adapter = Adapter(credentials, verified=False)
        adapters.append(adapter)
        return adapter
    connections, sessions, service = _service(tmp_path, vault, factory)
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(PermissionError, match="handshake"):
        service.connect(
            owner, provider_id="broker_a", account_alias="Conta",
            credential_ref="vault://tenant-a/broker-a",
        )
    assert sessions.status(owner) == []
    assert adapters[0].disconnected is True
    assert connections.list_connections(owner) == []


def test_connection_service_rejects_provider_handshake_with_order_capability(tmp_path):
    vault = Vault()
    adapters = []

    class TradingCapableAdapter(Adapter):
        def handshake(self):
            return {
                "provider_id": self.provider_id,
                "account_reference": "account-123",
                "capabilities": ["candles:read", "orders:write"],
                "verified": True,
            }

    def factory(credentials):
        adapter = TradingCapableAdapter(credentials)
        adapters.append(adapter)
        return adapter

    connections, sessions, service = _service(tmp_path, vault, factory)
    owner = TenantContext("tenant-a", "alice")

    with pytest.raises(PermissionError, match="somente leitura"):
        service.connect(
            owner, provider_id="broker_a", account_alias="Conta",
            credential_ref="vault://tenant-a/broker-a",
        )

    assert adapters[0].disconnected is True
    assert sessions.status(owner) == []
    assert connections.list_connections(owner) == []


@pytest.mark.parametrize(
    "capabilities",
    [
        ["candles:read", "orders:write"],
        ["candles:read", "account:admin"],
        ["quotes:stream"],
        [],
    ],
)
def test_connection_service_requires_allowlisted_candle_read_capabilities(
    tmp_path, capabilities
):
    vault = Vault()
    adapters = []

    class ScopedAdapter(Adapter):
        def handshake(self):
            return {
                "provider_id": self.provider_id,
                "account_reference": "account-123",
                "capabilities": capabilities,
                "verified": True,
            }

    def factory(credentials):
        adapter = ScopedAdapter(credentials)
        adapters.append(adapter)
        return adapter

    connections, sessions, service = _service(tmp_path, vault, factory)
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(PermissionError):
        service.connect(
            owner, provider_id="broker_a", account_alias="Conta",
            credential_ref="vault://tenant-a/broker-a",
        )
    assert adapters[0].disconnected is True
    assert sessions.status(owner) == []
    assert connections.list_connections(owner) == []


def test_connection_service_does_not_resolve_credentials_for_other_tenant(tmp_path):
    vault = Vault()
    _, sessions, service = _service(tmp_path, vault, lambda credentials: Adapter(credentials))
    other = TenantContext("tenant-b", "bob")
    with pytest.raises(PermissionError, match="não resolvida"):
        service.connect(
            other, provider_id="broker_a", account_alias="Conta",
            credential_ref="vault://tenant-a/broker-a",
        )
    assert sessions.status(other) == []


def test_disconnect_closes_adapter_and_revokes_runtime_binding(tmp_path):
    vault = Vault()
    adapters = []
    def factory(credentials):
        adapter = Adapter(credentials)
        adapters.append(adapter)
        return adapter
    connections, sessions, service = _service(tmp_path, vault, factory)
    owner = TenantContext("tenant-a", "alice")
    connected = service.connect(
        owner, provider_id="broker_a", account_alias="Conta",
        credential_ref="vault://tenant-a/broker-a",
    )
    result = service.disconnect(owner, connection_id=connected["connection_id"])
    assert result["status"] == "DISCONNECTED"
    assert adapters[0].disconnected is True
    assert sessions.get(owner, connection_id=connected["connection_id"]) is None
    assert connections.list_connections(owner)[0]["status"] == "DISCONNECTED"


def test_disconnect_revokes_stale_connected_metadata_after_process_restart(tmp_path):
    vault = Vault()
    connections, sessions, service = _service(tmp_path, vault, lambda credentials: Adapter(credentials))
    owner = TenantContext("tenant-a", "alice")
    connected = service.connect(
        owner, provider_id="broker_a", account_alias="Conta",
        credential_ref="vault://tenant-a/broker-a",
    )
    sessions.unbind(owner, connection_id=connected["connection_id"])
    result = service.disconnect(owner, connection_id=connected["connection_id"])
    assert result["status"] == "DISCONNECTED_SESSION_NOT_BOUND"
    assert connections.list_connections(owner)[0]["status"] == "DISCONNECTED"


def test_disconnect_service_can_revoke_account_without_vault_provisioned(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    sessions = TenantMarketDataSessionRegistry(connections)
    service = TenantProviderConnectionService(connections, sessions)
    owner = TenantContext("tenant-a", "alice")
    saved = connections.record_verified_connection(
        owner, provider_id="broker_a", account_alias="Conta",
        account_reference="account-123", capabilities=["candles:read"],
        adapter_verified=True,
    )
    result = service.disconnect(owner, connection_id=saved["connection_id"])
    assert result["status"] == "DISCONNECTED_SESSION_NOT_BOUND"
    assert connections.list_connections(owner)[0]["status"] == "DISCONNECTED"
    with pytest.raises(RuntimeError, match="cofre de credenciais"):
        service.connect(
            owner, provider_id="broker_a", account_alias="Conta",
            credential_ref="vault://tenant-a/broker-a",
        )


def test_provider_handshake_promotion_updates_reference_and_rejects_duplicate(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-promotion.sqlite3")
    connections = TenantProviderConnectionRegistry(storage)
    owner = TenantContext("tenant-a", "alice")
    first = connections.record_pending_connection(
        owner, provider_id="ctrader_open_api", account_alias="demo-a",
        account_reference="pending:first", capabilities=["candles:read"],
    )
    second = connections.record_pending_connection(
        owner, provider_id="ctrader_open_api", account_alias="demo-b",
        account_reference="pending:second", capabilities=["candles:read"],
    )
    assert connections.mark_connected_after_provider_handshake(
        owner, connection_id=first["connection_id"],
        account_reference="12345", capabilities=["candles:read", "candles:stream"],
    ) is True
    saved = next(item for item in connections.list_connections(owner) if item["connection_id"] == first["connection_id"])
    assert saved["status"] == "CONNECTED"
    assert saved["account_reference"] == "12345"
    assert saved["capabilities"] == ["candles:read", "candles:stream"]
    with pytest.raises(ValueError, match="já está vinculada"):
        connections.mark_connected_after_provider_handshake(
            owner, connection_id=second["connection_id"],
            account_reference="12345", capabilities=["candles:read"],
        )


def test_saved_provider_reconnects_after_process_restart_with_fresh_handshake(tmp_path):
    database = tmp_path / "tenant-provider-restart.sqlite3"
    owner = TenantContext("tenant-a", "alice")
    vault = Vault()
    first_adapters = []

    first_storage = SQLiteTenantStorage(database)
    first_connections = TenantProviderConnectionRegistry(first_storage)
    first_sessions = TenantMarketDataSessionRegistry(first_connections)
    first_service = TenantProviderConnectionService(
        first_connections, first_sessions, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: (
            first_adapters.append(Adapter(credentials)) or first_adapters[-1]
        )},
    )
    first = first_service.connect(
        owner, provider_id="broker_a", account_alias="Conta principal",
        credential_ref="vault://tenant-a/broker-a",
    )
    assert first["connection_id"]
    assert "credential_ref" not in first_connections.list_connections(owner)[0]

    # New registry/session/service objects represent a new application process.
    second_storage = SQLiteTenantStorage(database)
    second_connections = TenantProviderConnectionRegistry(second_storage)
    second_sessions = TenantMarketDataSessionRegistry(second_connections)
    second_adapters = []
    second_service = TenantProviderConnectionService(
        second_connections, second_sessions, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: (
            second_adapters.append(Adapter(credentials)) or second_adapters[-1]
        )},
    )
    restored_metadata = second_sessions.status(owner)
    assert len(restored_metadata) == 1
    assert restored_metadata[0]["adapter_status"] == "NOT_BOUND"
    assert restored_metadata[0]["health_status"] == "NOT_BOUND"
    assert second_sessions.get(owner, connection_id=first["connection_id"]) is None
    assert second_connections.list_connections(owner)[0]["status"] == "CONNECTED"

    recovered = second_service.reconnect_saved(
        owner, connection_id=first["connection_id"]
    )

    assert recovered["connection_id"] == first["connection_id"]
    assert recovered["status"] == "CONNECTED"
    assert recovered["adapter_status"] == "ADAPTER_BOUND"
    assert second_sessions.get(owner, connection_id=first["connection_id"]).adapter is second_adapters[0]
    assert second_adapters[0] is not first_adapters[0]
    assert vault.calls == [
        (owner, "vault://tenant-a/broker-a"),
        (owner, "vault://tenant-a/broker-a"),
    ]


def test_failed_saved_provider_reconnect_remains_disconnected(tmp_path):
    database = tmp_path / "tenant-provider-failed-restart.sqlite3"
    owner = TenantContext("tenant-a", "alice")
    vault = Vault()

    first_storage = SQLiteTenantStorage(database)
    first_connections = TenantProviderConnectionRegistry(first_storage)
    first_sessions = TenantMarketDataSessionRegistry(first_connections)
    first_service = TenantProviderConnectionService(
        first_connections, first_sessions, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: Adapter(credentials)},
    )
    first = first_service.connect(
        owner, provider_id="broker_a", account_alias="Conta principal",
        credential_ref="vault://tenant-a/broker-a",
    )

    second_storage = SQLiteTenantStorage(database)
    second_connections = TenantProviderConnectionRegistry(second_storage)
    second_sessions = TenantMarketDataSessionRegistry(second_connections)
    second_service = TenantProviderConnectionService(
        second_connections, second_sessions, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: Adapter(credentials, verified=False)},
    )

    with pytest.raises(PermissionError, match="handshake"):
        second_service.reconnect_saved(owner, connection_id=first["connection_id"])

    saved = second_connections.list_connections(owner)[0]
    assert saved["status"] == "DISCONNECTED"
    assert second_sessions.get(owner, connection_id=first["connection_id"]) is None


def test_startup_recovery_isolates_provider_failures_and_recovers_healthy_accounts(tmp_path):
    database = tmp_path / "tenant-provider-recovery-batch.sqlite3"
    owner = TenantContext("tenant-a", "alice")

    class MultiVault:
        def resolve(self, context, reference):
            if context.tenant_id != "tenant-a" or reference not in {
                "vault://tenant-a/broker-a", "vault://tenant-a/broker-b"
            }:
                return None
            return {"api_key": reference}

    vault = MultiVault()
    storage_one = SQLiteTenantStorage(database)
    connections_one = TenantProviderConnectionRegistry(storage_one)
    sessions_one = TenantMarketDataSessionRegistry(connections_one)
    initial = TenantProviderConnectionService(
        connections_one, sessions_one, secret_resolver=vault,
        adapter_factories={
            "broker_a": lambda credentials: Adapter(credentials, provider_id="broker_a"),
            "broker_b": lambda credentials: Adapter(credentials, provider_id="broker_b"),
        },
    )
    first = initial.connect(
        owner, provider_id="broker_a", account_alias="Conta A",
        credential_ref="vault://tenant-a/broker-a",
    )
    second = initial.connect(
        owner, provider_id="broker_b", account_alias="Conta B",
        credential_ref="vault://tenant-a/broker-b",
    )

    storage_two = SQLiteTenantStorage(database)
    connections_two = TenantProviderConnectionRegistry(storage_two)
    sessions_two = TenantMarketDataSessionRegistry(connections_two)
    recovered = TenantProviderConnectionService(
        connections_two, sessions_two, secret_resolver=vault,
        adapter_factories={
            "broker_a": lambda credentials: Adapter(credentials, provider_id="broker_a"),
            "broker_b": lambda credentials: Adapter(credentials, verified=False, provider_id="broker_b"),
        },
    )

    outcomes = recovered.reconnect_available(owner)
    by_id = {item["connection_id"]: item for item in outcomes}

    assert by_id[first["connection_id"]]["status"] == "RECONNECTED"
    assert by_id[second["connection_id"]]["status"] == "RECONNECT_FAILED"
    assert sessions_two.get(owner, connection_id=first["connection_id"]) is not None
    assert sessions_two.get(owner, connection_id=second["connection_id"]) is None
    saved = {item["connection_id"]: item for item in connections_two.list_connections(owner)}
    assert saved[first["connection_id"]]["status"] == "CONNECTED"
    assert saved[second["connection_id"]]["status"] == "DISCONNECTED"
    assert all(item["execution_authorized"] is False for item in outcomes)


def test_startup_recovery_does_not_reconnect_explicitly_disconnected_account(tmp_path):
    database = tmp_path / "tenant-provider-explicit-disconnect.sqlite3"
    owner = TenantContext("tenant-a", "alice")
    vault = Vault()
    storage_one = SQLiteTenantStorage(database)
    connections_one = TenantProviderConnectionRegistry(storage_one)
    sessions_one = TenantMarketDataSessionRegistry(connections_one)
    initial = TenantProviderConnectionService(
        connections_one, sessions_one, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: Adapter(credentials)},
    )
    account = initial.connect(
        owner, provider_id="broker_a", account_alias="Conta principal",
        credential_ref="vault://tenant-a/broker-a",
    )
    assert initial.disconnect(owner, connection_id=account["connection_id"])["status"] == "DISCONNECTED"

    storage_two = SQLiteTenantStorage(database)
    connections_two = TenantProviderConnectionRegistry(storage_two)
    sessions_two = TenantMarketDataSessionRegistry(connections_two)
    new_adapters = []
    restarted = TenantProviderConnectionService(
        connections_two, sessions_two, secret_resolver=vault,
        adapter_factories={"broker_a": lambda credentials: (
            new_adapters.append(Adapter(credentials)) or new_adapters[-1]
        )},
    )

    assert restarted.reconnect_available(owner) == []
    assert new_adapters == []
    assert connections_two.list_connections(owner)[0]["status"] == "DISCONNECTED"


def test_startup_recovery_reports_missing_provider_configuration(tmp_path):
    database = tmp_path / "tenant-provider-unconfigured-recovery.sqlite3"
    owner = TenantContext("tenant-a", "alice")
    storage = SQLiteTenantStorage(database)
    connections = TenantProviderConnectionRegistry(storage)
    sessions = TenantMarketDataSessionRegistry(connections)
    configured = TenantProviderConnectionService(
        connections, sessions, secret_resolver=Vault(),
        adapter_factories={"broker_a": lambda credentials: Adapter(credentials)},
    )
    account = configured.connect(
        owner, provider_id="broker_a", account_alias="Conta principal",
        credential_ref="vault://tenant-a/broker-a",
    )

    restarted = TenantProviderConnectionService(connections, sessions)
    outcomes = restarted.reconnect_available(owner)

    assert outcomes == [{
        "connection_id": account["connection_id"],
        "provider_id": "broker_a",
        "status": "RECOVERY_NOT_CONFIGURED",
        "execution_authorized": False,
    }]
    assert sessions.get(owner, connection_id=account["connection_id"]) is not None



def test_ctrader_startup_recovery_is_delegated_to_oauth_aware_account_service(tmp_path):
    database = tmp_path / "tenant-provider-ctrader-delegated.sqlite3"
    owner = TenantContext("tenant-a", "alice")
    storage = SQLiteTenantStorage(database)
    connections = TenantProviderConnectionRegistry(storage)
    sessions = TenantMarketDataSessionRegistry(connections)
    initial = TenantProviderConnectionService(
        connections, sessions, secret_resolver=Vault(),
        adapter_factories={"ctrader": lambda credentials: Adapter(
            credentials, provider_id="ctrader"
        )},
    )
    account = initial.connect(
        owner, provider_id="ctrader", account_alias="cTrader DEMO",
        credential_ref="vault://tenant-a/broker-a",
    )
    calls = []
    restarted = TenantProviderConnectionService(
        connections, sessions, secret_resolver=Vault(),
        adapter_factories={"ctrader": lambda credentials: (
            calls.append(credentials) or Adapter(credentials, provider_id="ctrader")
        )},
    )

    outcomes = restarted.reconnect_available(owner)

    assert outcomes == [{
        "connection_id": account["connection_id"],
        "provider_id": "ctrader",
        "status": "RECOVERY_DELEGATED",
        "recovery_owner": "TENANT_CTRADER_ACCOUNT_SERVICE",
        "execution_authorized": False,
    }]
    assert calls == []
    assert sessions.get(owner, connection_id=account["connection_id"]) is None
