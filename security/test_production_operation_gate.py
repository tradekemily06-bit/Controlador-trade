import pytest

from security.production_operation_gate import ProductionOperationGate
from storage.production_boundary import ProductionStoragePolicy


def test_gate_fails_closed_when_storage_is_not_ready():
    gate = ProductionOperationGate(ProductionStoragePolicy())

    with pytest.raises(PermissionError, match="storage is not ready"):
        gate.authorize(subject_id="user-a", tenant_id="tenant-a")


def test_gate_requires_trusted_subject_and_tenant_before_storage_check():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=True,
        durable=True,
    )
    gate = ProductionOperationGate(policy)

    with pytest.raises(PermissionError, match="production subject is required"):
        gate.authorize(subject_id=None, tenant_id="tenant-a")

    with pytest.raises(PermissionError, match="production tenant is required"):
        gate.authorize(subject_id="user-a", tenant_id=None)


def test_gate_authorizes_only_explicitly_ready_scoped_storage():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=True,
        durable=True,
    )
    gate = ProductionOperationGate(policy)

    context = gate.authorize(subject_id="  user-a  ", tenant_id="  tenant-a  ")

    assert context.subject_id == "user-a"
    assert context.tenant_id == "tenant-a"
    assert gate.status() == {
        "authorized": False,
        "storage_state": "READY",
        "real_execution": "DESABILITADO",
    }


def test_gate_rejects_unsafe_storage_even_with_identity():
    policy = ProductionStoragePolicy(
        provider_configured=True,
        tenant_scoped=False,
        durable=True,
    )
    gate = ProductionOperationGate(policy)

    with pytest.raises(PermissionError, match="storage is not ready"):
        gate.authorize(subject_id="user-a", tenant_id="tenant-a")
