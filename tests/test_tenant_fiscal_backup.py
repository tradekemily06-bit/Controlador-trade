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


def test_backup_restore_is_validated_in_temporary_database(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    service = TenantFiscalBackupService(factory, backups)
    alice_context = TenantContext("tenant-a", "alice")
    alice = factory.get(alice_context)
    alice.foreign_pending.add(alice.owner_id, _pending("ALICE-RESTORE-TEST"))

    created = service.backup(alice_context)
    assert created["status"] == "BACKUP_CREATED"
    live_path = alice.database_path
    before = sqlite3.connect(live_path).execute(
        "SELECT reference FROM fiscal_reserve_pending_foreign"
    ).fetchall()

    verified = service.verify_restore(alice_context, created["filename"])

    assert verified == {
        "status": "RESTORE_VALIDATED_IN_ISOLATION",
        "scope": "ONE_TENANT_AND_SUBJECT",
        "live_database_modified": False,
        "backup_filename": created["filename"],
        "execution_authorized": False,
    }
    after = sqlite3.connect(live_path).execute(
        "SELECT reference FROM fiscal_reserve_pending_foreign"
    ).fetchall()
    assert after == before
    assert not list(backups.glob(".tenant-restore-test-*"))


def test_restore_verification_rejects_another_subjects_backup(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    service = TenantFiscalBackupService(factory, backups)
    alice_context = TenantContext("tenant-a", "alice")
    bob_context = TenantContext("tenant-a", "bob")
    alice = factory.get(alice_context)
    alice.foreign_pending.add(alice.owner_id, _pending("ALICE-ONLY"))
    created = service.backup(alice_context)

    with pytest.raises(ValueError, match="não pertence"):
        service.verify_restore(bob_context, created["filename"])


def test_restore_verification_rejects_path_traversal(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path / "runtime")
    service = TenantFiscalBackupService(factory, tmp_path / "backups")
    context = TenantContext("tenant-a", "alice")
    with pytest.raises(ValueError, match="nome de backup"):
        service.verify_restore(context, "../tenant-fiscal-other.sqlite3")


def test_tenant_fiscal_backup_rejects_broken_foreign_key_relations(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    context = TenantContext("tenant-a", "alice")
    repositories = factory.get(context)
    with sqlite3.connect(repositories.database_path) as db:
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute(
            """INSERT INTO fiscal_pending_reviews
               (review_id, owner_id, pending_id, candidate_classification,
                confirmed_jurisdiction, reviewer_name, reviewer_role,
                professional_registration, evidence_reference, reviewed_on,
                review_notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("bad-review", repositories.owner_id, "missing-pending",
             "UNCLASSIFIED", "US", "Test Reviewer", "TEST",
             "TEST-REG", "test-evidence", "2026-11-27", "", "2026-11-27T00:00:00Z"),
        )

    service = TenantFiscalBackupService(factory, backups)
    result = service.backup(context)

    assert result["status"] == "BACKUP_FAILED"
    assert result["scope"] == "ONE_TENANT_AND_SUBJECT"
    assert not list(backups.glob("tenant-fiscal-*.sqlite3"))


def test_scheduled_backup_covers_all_managed_fiscal_shards_without_crossing_owners(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    alice_context = TenantContext("tenant-a", "alice")
    bob_context = TenantContext("tenant-a", "bob")
    alice = factory.get(alice_context)
    bob = factory.get(bob_context)
    alice.foreign_pending.add(alice.owner_id, _pending("ALICE-SCHEDULED"))
    bob.foreign_pending.add(bob.owner_id, _pending("BOB-SCHEDULED"))

    service = TenantFiscalBackupService(factory, backups)
    result = service.backup_all_managed_shards()

    assert result["status"] == "SUCCESS"
    assert len(result["results"]) == 2
    assert {item["status"] for item in result["results"]} == {"BACKUP_CREATED"}
    for item in result["results"]:
        assert item["owner_digest"] not in {"alice", "bob"}
        with sqlite3.connect(backups / item["filename"]) as db:
            owners = {
                row[0] for row in db.execute(
                    "SELECT DISTINCT owner_id FROM fiscal_reserve_pending_foreign"
                ).fetchall()
            }
            refs = {
                row[0] for row in db.execute(
                    "SELECT reference FROM fiscal_reserve_pending_foreign"
                ).fetchall()
            }
        assert len(owners) == 1
        assert refs in ({"ALICE-SCHEDULED"}, {"BOB-SCHEDULED"})


def test_scheduled_tenant_backup_fails_closed_on_unexpected_shard_file(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    context = TenantContext("tenant-a", "alice")
    factory.get(context)
    (factory.tenant_root / "unexpected").mkdir()
    service = TenantFiscalBackupService(factory, backups)

    result = service.backup_all_managed_shards()

    assert result["status"] == "SOURCE_UNSAFE"
    assert result["results"] == []


def test_scheduled_tenant_backup_rejects_owner_digest_mismatch(tmp_path):
    runtime = tmp_path / "runtime"
    backups = tmp_path / "backups"
    factory = TenantFiscalStoreFactory(runtime)
    context = TenantContext("tenant-a", "alice")
    repositories = factory.get(context)
    with sqlite3.connect(repositories.database_path) as db:
        db.execute(
            "UPDATE fiscal_reserve_settings SET owner_id = ?",
            ("tenant:" + "0" * 64,),
        )

    result = TenantFiscalBackupService(factory, backups).backup_all_managed_shards()

    assert result["status"] == "PARTIAL_OR_FAILED"
    assert result["results"][0]["status"] == "BACKUP_FAILED"
    assert not list(backups.glob("tenant-fiscal-*.sqlite3"))
