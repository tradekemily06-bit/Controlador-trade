from datetime import datetime, timezone

import pytest

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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


def test_reserved_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reserved")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.unknown_request_ids == ("req-reserved",)


def test_unknown_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-unknown")
    coordinator.execution_ledger.mark_unknown("req-unknown")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.unknown_request_ids == ("req-unknown",)


def _assert_requires_reconciliation(coordinator):
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_lifecycle_unknown_cannot_pair_with_terminal_ledger(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.UNKNOWN, now))
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_accepted("req-mismatch", "ext-1")
    _assert_requires_reconciliation(coordinator)


def test_lifecycle_accepted_cannot_pair_with_reconciled_not_executed(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.ACCEPTED, now))
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_unknown("req-mismatch")
    coordinator.execution_ledger.reconcile_observation(
        "req-mismatch",
        __import__("core.p121_external_order_reconciliation", fromlist=["ExternalOrderObservation", "ExternalOrderStatus"]).ExternalOrderObservation(
            None,
            __import__("core.p121_external_order_reconciliation", fromlist=["ExternalOrderStatus"]).ExternalOrderStatus.NOT_EXECUTED,
            "not found",
            request_id="req-mismatch",
        ),
    )
    _assert_requires_reconciliation(coordinator)


def test_lifecycle_rejected_can_pair_with_reconciled_not_executed(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-rejected", ExecutionLifecycleState.REJECTED, now))
    coordinator.execution_ledger.reserve("req-rejected")
    coordinator.execution_ledger.mark_unknown("req-rejected")
    from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
    coordinator.execution_ledger.reconcile_observation(
        "req-rejected", ExternalOrderObservation(None, ExternalOrderStatus.NOT_EXECUTED, "confirmed", request_id="req-rejected")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.FRESH


def test_lifecycle_pending_cannot_pair_with_terminal_ledger(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.reserve("req-pending")
    coordinator.execution_ledger.mark_rejected("req-pending")
    _assert_requires_reconciliation(coordinator)


def test_lifecycle_only_rejected_is_not_safe_to_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-only", ExecutionLifecycleState.REJECTED, now))
    _assert_requires_reconciliation(coordinator)


def test_ledger_only_accepted_is_not_safe_to_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-only")
    coordinator.execution_ledger.mark_accepted("req-only", "ext-only")
    _assert_requires_reconciliation(coordinator)


def test_ledger_only_reconciled_executed_is_not_safe_to_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-only")
    coordinator.execution_ledger.mark_unknown("req-only")
    from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
    coordinator.execution_ledger.reconcile_observation(
        "req-only", ExternalOrderObservation("ext-only", ExternalOrderStatus.EXECUTED, "confirmed", request_id="req-only")
    )
    _assert_requires_reconciliation(coordinator)
