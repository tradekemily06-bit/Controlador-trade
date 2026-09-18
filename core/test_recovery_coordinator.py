from datetime import datetime, timezone

import pytest

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def make_coordinator(tmp_path):
    return RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
        memory=OperationMemory(),
    )


def test_fresh_session_is_safe(tmp_path):
    result = make_coordinator(tmp_path).assess()
    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_checkpoint_allows_safe_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(RuntimeCheckpoint("s1", 3, "req-3", datetime.now(timezone.utc)))
    result = coordinator.assess()
    assert result.state is RecoveryState.SAFE_TO_RESUME
    assert result.checkpoint.last_cycle == 3


def test_unknown_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.unknown_request_ids == ("req-1",)


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
            memory=OperationMemory(),
        )

def test_orphaned_reserved_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reserved")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert "RESERVED/UNKNOWN" in result.message

def test_terminal_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-terminal")
    coordinator.execution_ledger.mark_accepted("req-terminal")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert "ledger terminal sem lifecycle" in result.message


def test_mismatched_terminal_states_require_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_accepted("req-mismatch")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.REJECTED, now, "mismatch")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False



def test_reconciled_executed_with_accepted_lifecycle_is_safe(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=True)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.ACCEPTED, now, "reconciled")
    )

    result = coordinator.assess()

    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_reconciled_not_executed_with_rejected_lifecycle_is_safe(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=False)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.REJECTED, now, "reconciled")
    )

    result = coordinator.assess()

    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


@pytest.mark.parametrize(
    ("lifecycle_state", "ledger_state"),
    [
        (ExecutionLifecycleState.ACCEPTED, "REJECTED"),
        (ExecutionLifecycleState.REJECTED, "ACCEPTED"),
        (ExecutionLifecycleState.PENDING, "ACCEPTED"),
        (ExecutionLifecycleState.PENDING, "REJECTED"),
        (ExecutionLifecycleState.UNKNOWN, "ACCEPTED"),
        (ExecutionLifecycleState.UNKNOWN, "REJECTED"),
    ],
)
def test_any_lifecycle_terminal_or_uncertain_mismatch_blocks_resume(tmp_path, lifecycle_state, ledger_state):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-cross-mismatch")
    if ledger_state == "ACCEPTED":
        coordinator.execution_ledger.mark_accepted("req-cross-mismatch")
    else:
        coordinator.execution_ledger.mark_rejected("req-cross-mismatch")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-cross-mismatch", lifecycle_state, now, "cross-store mismatch")
    )

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_corrupt_lifecycle_blocks_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    (tmp_path / "lifecycle.json").write_text('{"not": "a list"}', encoding="utf-8")

    result = coordinator.assess()

    assert result.state is RecoveryState.INVALID
    assert result.can_resume is False


def test_corrupt_ledger_blocks_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    (tmp_path / "ledger.json").write_text('{"req-1": "NOT_A_REAL_STATE"}', encoding="utf-8")

    result = coordinator.assess()

    assert result.state is RecoveryState.INVALID
    assert result.can_resume is False


def test_reconciled_terminal_without_lifecycle_still_blocks_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reconciled-orphan")
    coordinator.execution_ledger.reconcile("req-reconciled-orphan", executed=True)

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
