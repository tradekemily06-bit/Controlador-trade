import pytest

from storage.production_boundary import ProductionStoragePolicy, UnconfiguredProductionStore


def test_storage_policy_reports_unconfigured_state():
    policy = ProductionStoragePolicy()
    assert policy.status()["state"] == "NOT_CONFIGURED"
    assert policy.status()["tenant_scope"] == "ENFORCED"
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-1") is False


def test_storage_policy_requires_identity_and_tenant_when_ready():
    policy = ProductionStoragePolicy(
        required=True,
        provider_configured=True,
        tenant_scoped=True,
        durable=True,
    )
    assert policy.status()["state"] == "READY"
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-1") is True
    assert policy.authorize_write(authenticated=False, tenant_id="tenant-1") is False
    assert policy.authorize_write(authenticated=True, tenant_id=" ") is False


def test_unconfigured_store_fails_closed():
    store = UnconfiguredProductionStore()
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.save({"id": "1"}, tenant_id="tenant-1")
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.load("1", tenant_id="tenant-1")
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.list(tenant_id="tenant-1")
