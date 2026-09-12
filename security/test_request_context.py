import pytest

from security.request_context import ProductionRequestContext, require_production_context


def test_context_requires_subject_and_tenant():
    with pytest.raises(PermissionError):
        require_production_context(subject_id=None, tenant_id="tenant-a")
    with pytest.raises(PermissionError):
        require_production_context(subject_id="user-a", tenant_id=None)


def test_context_normalizes_and_reports_tenant_scope():
    context = require_production_context(subject_id=" user-a ", tenant_id=" tenant-a ")
    assert context == ProductionRequestContext(subject_id="user-a", tenant_id="tenant-a")
    assert context.is_valid() is True
    assert context.status() == {"authenticated": "YES", "tenant_scope": "SET"}


def test_context_rejects_blank_values():
    with pytest.raises(PermissionError):
        require_production_context(subject_id=" ", tenant_id="tenant-a")
    with pytest.raises(PermissionError):
        require_production_context(subject_id="user-a", tenant_id=" ")
