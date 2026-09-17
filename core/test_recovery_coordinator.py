from datetime import datetime, timezone

import pytest

from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def make_coordinator(tmp_path):
    return RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    )


def test_fresh_session_is_safe(tmp_path):
    result = make_coordinator(tmp_path).assess()
    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_checkpoint_allows_safe_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-3", ExecutionLifecycleState.REJECTED, now, "rejected"))
    coordinator.execution_ledger.reserve("req-3")
    coordinator.execution_ledger.mark_rejected("req-3")
    coordinator.checkpoint_store.save(RuntimeCheckpoint("s1", 3, "req-3", now))
    result = coordinator.assess(session_id="s1")
    assert result.state is RecoveryState.SAFE_TO_RESUME
    assert result.checkpoint.last_cycle == 3


def test_checkpoint_from_different_session_cannot_resume_implicitly(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-3", ExecutionLifecycleState.REJECTED, now, "rejected"))
    coordinator.execution_ledger.reserve("req-3")
    coordinator.execution_ledger.mark_rejected("req-3")
    coordinator.checkpoint_store.save(RuntimeCheckpoint("old-session", 3, "req-3", now))
    result = coordinator.assess(session_id="new-session")
    assert result.state is RecoveryState.SESSION_MISMATCH
    assert result.can_resume is False
    assert result.checkpoint.session_id == "old-session"


def test_orphan_checkpoint_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(RuntimeCheckpoint("s1", 3, "missing-request", datetime.now(timezone.utc)))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert "checkpoint" in result.message


def test_unknown_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.unknown_request_ids == ("req-1",)


def test_orphan_uncertain_ledger_requires_reconciliation_even_without_lifecycle(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-orphan")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.unknown_request_ids == ("req-orphan",)


def test_lifecycle_terminal_state_diverging_from_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-divergent", ExecutionLifecycleState.ACCEPTED, now, "accepted"))
    coordinator.execution_ledger.reserve("req-divergent")
    coordinator.execution_ledger.mark_unknown("req-divergent")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_terminal_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-ledger-only")
    coordinator.execution_ledger.mark_accepted("req-ledger-only")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_reconciled_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reconciled-only")
    coordinator.execution_ledger.mark_unknown("req-reconciled-only")
    coordinator.execution_ledger.reconcile(
        "req-reconciled-only",
        executed=False,
        evidence_id="evidence-1",
        evidence_source="demo-broker",
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_pending_requires_verification(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.pending_request_ids == ("req-1",)


def test_accepted_without_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION


def test_invalid_checkpoint_fails_closed(tmp_path):
    coordinator = make_coordinator(tmp_path)
    (tmp_path / "checkpoint.json").write_text("{bad", encoding="utf-8")
    result = coordinator.assess()
    assert result.state is RecoveryState.INVALID
    assert result.can_resume is False


def test_dependencies_are_required(tmp_path):
    with pytest.raises(ValueError):
        RecoveryCoordinator(
            checkpoint_store=None,
            lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
            execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
        )
