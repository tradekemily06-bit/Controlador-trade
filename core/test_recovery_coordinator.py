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


def test_reserved_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reserved")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.pending_request_ids == ("req-reserved",)
    assert result.can_resume is False


def test_unknown_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-unknown")
    coordinator.execution_ledger.mark_unknown("req-unknown")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.unknown_request_ids == ("req-unknown",)
    assert result.can_resume is False



def test_lifecycle_and_ledger_terminal_states_must_match(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.ACCEPTED, now)
    )
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_rejected("req-mismatch")

    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert "req-mismatch" not in result.pending_request_ids


def test_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-orphan")

    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.pending_request_ids == ("req-orphan",)


def test_checkpoint_request_without_execution_state_blocks_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(
        RuntimeCheckpoint("s1", 4, "missing-request", datetime.now(timezone.utc))
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_recovery_allows_checkpoint_without_request_id(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(
        RuntimeCheckpoint("s1", 4, None, datetime.now(timezone.utc))
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.SAFE_TO_RESUME


def test_recovery_uses_single_ledger_snapshot(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("snapshot")
    snapshot_calls = {"count": 0}
    original = coordinator.execution_ledger.snapshot

    def counted_snapshot():
        snapshot_calls["count"] += 1
        return original()

    coordinator.execution_ledger.snapshot = counted_snapshot
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert snapshot_calls["count"] == 1
