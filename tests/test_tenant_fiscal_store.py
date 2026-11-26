from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from finance.fiscal_schema import migrate_fiscal_schema
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


def _foreign_item(reference: str) -> dict[str, object]:
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    return {
        "reference": reference,
        "original_amount": 125.50,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": today,
        "fx_rate": 5.42,
        "fx_date": today,
        "fx_source": "documento de teste",
        "fx_conversion_method": "PTAX_SELL",
    }


def test_tenant_fiscal_factory_separates_subject_databases_and_records(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path)
    alice_context = TenantContext(tenant_id="tenant-a", subject_id="alice")
    bob_context = TenantContext(tenant_id="tenant-a", subject_id="bob")

    alice = factory.get(alice_context)
    bob = factory.get(bob_context)

    assert alice.database_path != bob.database_path
    assert alice.owner_id != bob.owner_id
    assert "tenant-a" not in alice.database_path
    assert "alice" not in alice.database_path
    assert "bob" not in bob.database_path
    assert factory.get(alice_context) is alice

    alice.foreign_pending.add(alice.owner_id, _foreign_item("ALICE-ONLY"))
    assert [item["reference"] for item in alice.foreign_pending.list_pending(alice.owner_id)["items"]] == [
        "ALICE-ONLY"
    ]
    assert bob.foreign_pending.list_pending(bob.owner_id)["items"] == []


def test_tenant_fiscal_factory_requires_tenant_context_not_raw_ids(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path)
    with pytest.raises(TypeError, match="TenantContext confiável"):
        factory.get({"tenant_id": "tenant-a", "subject_id": "alice"})  # type: ignore[arg-type]


def test_tenant_fiscal_migration_rejects_nonopaque_owner_key(tmp_path):
    database = tmp_path / "must-not-be-created.sqlite3"
    with pytest.raises(ValueError, match="chave opaca confiável"):
        migrate_fiscal_schema(str(database), trusted_owner_id="tenant:alice")
    assert not database.exists()
