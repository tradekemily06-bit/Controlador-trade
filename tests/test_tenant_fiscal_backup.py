from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core.tenant_fiscal_backup import TenantFiscalBackupService
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


def _pending(reference: str) -> dict[str, object]:
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    return {
        "reference": reference,
        "original_amount": 250.0,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": today,
    }


def test_backup_contains_only_the_requested_tenant_database(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    service = TenantFiscalBackupService(factory, backups)
    alice = factory.get(TenantContext("tenant-a", "alice"))
    bob = factory.get(TenantContext("tenant-a", "bob"))
    alice.foreign_pending.add(alice.owner_id, _pending("ALICE-RECORD"))
    bob.foreign_pending.add(bob.owner_id, _pending("BOB-RECORD"))

    result = service.backup(TenantContext("tenant-a", "alice"))

    assert result["status"] == "BACKUP_CREATED"
    assert result["scope"] == "ONE_TENANT_AND_SUBJECT"
    assert result["restore_tested"] is False
    backup = backups / result["filename"]
    with sqlite3.connect(backup) as db:
        references = {
            row[0]
            for row in db.execute(
                "SELECT reference FROM fiscal_reserve_pending_foreign"
            ).fetchall()
        }
    assert references == {"ALICE-RECORD"}
    assert "alice" not in result["filename"]
    assert "tenant-a" not in result["filename"]


def test_tenant_backup_rejects_untrusted_context_shape(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path / "runtime")
    service = TenantFiscalBackupService(factory, tmp_path / "backups")
    with pytest.raises(TypeError, match="TenantContext confiável"):
        service.backup({"tenant_id": "tenant-a", "subject_id": "alice"})  # type: ignore[arg-type]


def test_tenant_backup_directory_must_be_outside_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    factory = TenantFiscalStoreFactory(runtime)
    with pytest.raises(ValueError, match="outside runtime"):
        TenantFiscalBackupService(factory, runtime / "backups")
