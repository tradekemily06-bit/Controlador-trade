import pytest

from storage.production_boundary import ProductionStoragePolicy, UnconfiguredProductionStore


def test_default_storage_is_fail_closed():
    policy = ProductionStoragePolicy()
    assert policy.status()["state"] == "NOT_CONFIGURED"
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-a", subject_id="user-a") is False
    assert policy.authorize_read(authenticated=True, tenant_id="tenant-a", subject_id="user-a") is False


def test_ready_storage_requires_identity_tenant_and_subject():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=True,
        subject_scoped=True,
        durable=True,
    )
    assert policy.status()["state"] == "READY"
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-a", subject_id="user-a") is True
    assert policy.authorize_read(authenticated=True, tenant_id="tenant-a", subject_id="user-a") is True
    assert policy.authorize_write(authenticated=False, tenant_id="tenant-a", subject_id="user-a") is False
    assert policy.authorize_write(authenticated=True, tenant_id=" ", subject_id="user-a") is False
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-a", subject_id=" ") is False


def test_subject_scope_is_required_even_when_tenant_scope_is_ready():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=True,
        subject_scoped=False,
        durable=True,
    )
    assert policy.status()["state"] == "UNSAFE_SUBJECT_SCOPE"
    assert policy.authorize_write(authenticated=True, tenant_id="tenant-a", subject_id="user-a") is False


def test_unsafe_or_non_durable_storage_is_rejected():
    assert ProductionStoragePolicy(provider_configured=True, tenant_scoped=False, durable=True).status()["state"] == "UNSAFE_TENANT_SCOPE"
    assert ProductionStoragePolicy(provider_configured=True, tenant_scoped=True, subject_scoped=True, durable=False).status()["state"] == "NOT_DURABLE"


def test_unconfigured_store_fails_closed():
    store = UnconfiguredProductionStore()
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.save({"id": "1"}, tenant_id="tenant-a", subject_id="user-a")
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.load("1", tenant_id="tenant-a", subject_id="user-a")
    with pytest.raises(RuntimeError, match="storage provider is not configured"):
        store.list(tenant_id="tenant-a", subject_id="user-a")
