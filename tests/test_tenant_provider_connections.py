from concurrent.futures import ThreadPoolExecutor

import pytest

from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_provider_connections import TenantProviderConnectionRegistry


def _registry(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    return TenantProviderConnectionRegistry(storage)


def test_only_verified_adapter_can_register_broker_connection(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    with pytest.raises(PermissionError, match="verified adapter handshake"):
        registry.record_verified_connection(
            alice, provider_id="broker_x", account_alias="Conta principal",
            account_reference="account-123", adapter_verified=False,
        )
    assert registry.list_connections(alice) == []


def test_broker_connections_are_isolated_by_tenant_and_subject(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-b", "bob")
    connection = registry.record_verified_connection(
        alice, provider_id="broker_x", account_alias="Conta principal",
        account_reference="account-123", capabilities=["candles:read", "quotes:read"],
        adapter_verified=True,
    )
    assert connection["status"] == "CONNECTED"
    assert connection["read_only"] is True
    assert connection["execution_authorized"] is False
    assert registry.list_connections(bob) == []
    assert registry.list_connections(alice)[0]["connection_id"] == connection["connection_id"]


def test_registry_never_returns_credentials_or_unapproved_metadata(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    registry.record_verified_connection(
        alice, provider_id="broker_x", account_alias="Conta",
        account_reference="account-123", capabilities=["candles:read"],
        adapter_verified=True,
    )
    record = registry.list_connections(alice)[0]
    assert set(record) == {
        "connection_id", "provider_id", "account_alias", "account_reference",
        "status", "last_verified_at", "capabilities", "read_only",
        "execution_authorized",
    }
    assert not any("token" in key or "secret" in key or "password" in key for key in record)


def test_reverification_updates_same_broker_account_and_disconnect_is_owner_scoped(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-b", "bob")
    first = registry.record_verified_connection(
        alice, provider_id="broker_x", account_alias="Conta",
        account_reference="account-123", capabilities=["candles:read"],
        adapter_verified=True,
    )
    second = registry.record_verified_connection(
        alice, provider_id="broker_x", account_alias="Conta atualizada",
        account_reference="account-123", capabilities=["candles:read", "quotes:read"],
        adapter_verified=True,
    )
    assert first["connection_id"] == second["connection_id"]
    assert second["account_alias"] == "Conta atualizada"
    assert registry.mark_disconnected(bob, connection_id=first["connection_id"]) is False
    assert registry.mark_disconnected(alice, connection_id=first["connection_id"]) is True
    assert registry.list_connections(alice)[0]["status"] == "DISCONNECTED"


def test_registry_requires_trusted_tenant_context(tmp_path):
    registry = _registry(tmp_path)
    with pytest.raises(PermissionError, match="trusted tenant context"):
        registry.list_connections(None)


def test_concurrent_accounts_do_not_overwrite_each_other(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")

    def connect(index):
        return registry.record_verified_connection(
            alice, provider_id="broker_x", account_alias=f"Conta {index}",
            account_reference=f"account-{index}", adapter_verified=True,
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(connect, range(24)))

    listed = registry.list_connections(alice)
    assert len(results) == 24
    assert len(listed) == 24
    assert len({item["account_reference"] for item in listed}) == 24
    assert len({item["connection_id"] for item in listed}) == 24


def test_concurrent_reverification_preserves_connection_identity(tmp_path):
    registry = _registry(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    first = registry.record_verified_connection(
        alice, provider_id="broker_x", account_alias="Conta",
        account_reference="account-123", adapter_verified=True,
    )

    def verify(index):
        return registry.record_verified_connection(
            alice, provider_id="broker_x", account_alias=f"Conta {index}",
            account_reference="account-123", adapter_verified=True,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(verify, range(16)))

    assert all(item["connection_id"] == first["connection_id"] for item in results)
    assert len(registry.list_connections(alice)) == 1
