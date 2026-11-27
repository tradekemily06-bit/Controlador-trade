import pytest

from assistant.tenant_read_only_context import collect_tenant_fiscal_context
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


def test_tenant_fiscal_context_resolves_only_the_requested_owner(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path)
    alice_identity = TenantContext("tenant-a", "alice")
    bob_identity = TenantContext("tenant-a", "bob")

    alice_context = collect_tenant_fiscal_context(factory, alice_identity)
    bob_context = collect_tenant_fiscal_context(factory, bob_identity)
    alice_repositories = factory.get(alice_identity)
    bob_repositories = factory.get(bob_identity)

    assert alice_repositories.owner_id != bob_repositories.owner_id
    assert alice_repositories.database_path != bob_repositories.database_path
    for context in (alice_context, bob_context):
        assert context["scope"] == "TENANT_AND_SUBJECT"
        assert context["operational_context"] == "NOT_INCLUDED_SHARED_STATE"
        assert "system" not in context
        assert "risk" not in context
        assert "operations" not in context
        assert "statistics" not in context
        assert "recent_decisions" not in context
        assert "fiscal_reserve" in context
        assert context["assistant_safety"]["read_only"] is True
        assert context["assistant_safety"]["may_execute_orders"] is False


def test_tenant_fiscal_context_rejects_caller_supplied_repositories_and_identity():
    factory = TenantFiscalStoreFactory(".")
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context({"get": lambda _: None}, TenantContext("tenant-a", "alice"))
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context(factory, {"tenant_id": "tenant-a", "subject_id": "alice"})
