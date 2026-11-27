from types import SimpleNamespace

import pytest

from assistant.tenant_read_only_context import collect_tenant_fiscal_context
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


def test_tenant_fiscal_context_uses_only_owner_repositories(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path)
    alice = factory.get(TenantContext("tenant-a", "alice"))
    bob = factory.get(TenantContext("tenant-a", "bob"))

    alice_context = collect_tenant_fiscal_context(alice)
    bob_context = collect_tenant_fiscal_context(bob)

    assert alice.owner_id != bob.owner_id
    assert alice.database_path != bob.database_path
    for context in (alice_context, bob_context):
        assert context["scope"] == "TENANT_AND_SUBJECT"
        assert context["operational_context"] == "NOT_INCLUDED_SHARED_STATE"
        assert "system" not in context
        assert "risk" not in context
        assert "operations" not in context
        assert "statistics" not in context
        assert "recent_decisions" not in context
        assert "fiscal_reserve" in context


def test_tenant_fiscal_context_rejects_unbundled_or_untrusted_objects():
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context({"owner_id": "caller-controlled"})
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context(SimpleNamespace(owner_id="x", reserve=object()))
