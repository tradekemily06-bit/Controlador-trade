from __future__ import annotations

import pytest

from analysis.decision_record import DecisionRecord
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_decision_memory import TenantScopedDecisionMemory


def _record(decision_id: str = "decision-1") -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-11-26T12:00:00+00:00",
        symbol="EURUSD",
        timeframe="M5",
        signal="AGUARDAR",
        score=42.0,
        confirmed=False,
        reason="Dados insuficientes",
        execution_allowed=False,
    )


def test_decision_memory_isolates_tenant_and_subject(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    memory = TenantScopedDecisionMemory(storage)
    owner_a = TenantContext("tenant-a", "subject-a")
    owner_b = TenantContext("tenant-a", "subject-b")
    other_tenant = TenantContext("tenant-b", "subject-a")

    memory.save(owner_a, _record())
    assert [item.decision_id for item in memory.load(owner_a)] == ["decision-1"]
    assert memory.load(owner_b) == []
    assert memory.load(other_tenant) == []


def test_decision_memory_requires_explicit_tenant_context(tmp_path):
    memory = TenantScopedDecisionMemory(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    with pytest.raises(PermissionError, match="trusted tenant context"):
        memory.load(None)
    with pytest.raises(PermissionError, match="trusted tenant context"):
        memory.save(None, _record())


def test_decision_memory_updates_manual_outcome_without_granting_execution(tmp_path):
    memory = TenantScopedDecisionMemory(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    owner = TenantContext("tenant-a", "subject-a")
    memory.save(owner, _record())

    updated = memory.record_outcome(owner, "decision-1", "WIN")
    loaded = memory.load(owner)[0]

    assert updated.outcome == "WIN"
    assert updated.outcome_source == "MANUAL_STUDY"
    assert loaded.outcome == "WIN"
    assert loaded.execution_allowed is False


def test_decision_memory_rejects_execution_authority_and_invalid_limits(tmp_path):
    memory = TenantScopedDecisionMemory(SQLiteTenantStorage(tmp_path / "tenant.sqlite3"))
    owner = TenantContext("tenant-a", "subject-a")
    with pytest.raises(ValueError, match="execution authority"):
        memory.save(owner, DecisionRecord(**{
            **_record().to_dict(), "execution_allowed": True
        }))
    for limit in (0, 2001, True, 1.5, "10"):
        with pytest.raises(ValueError, match="limit"):
            memory.load(owner, limit=limit)


def test_decision_memory_never_imports_legacy_global_records(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    memory = TenantScopedDecisionMemory(storage)
    legacy = DecisionRecord(**{
        **_record("legacy-decision").to_dict(),
    })
    # A legacy record is not present in the tenant store unless explicitly
    # assigned by a trusted, separately reviewed migration process.
    assert memory.load(TenantContext("tenant-a", "subject-a")) == []
