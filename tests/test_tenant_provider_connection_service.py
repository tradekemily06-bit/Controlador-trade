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


def test_connection_service_does_not_resolve_credentials_for_other_tenant(tmp_path):
    vault = Vault()
    _, sessions, service = _service(tmp_path, vault, lambda credentials: Adapter(credentials))
    other = TenantContext("tenant-b", "bob")
    with pytest.raises(PermissionError, match="not resolved"):
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
