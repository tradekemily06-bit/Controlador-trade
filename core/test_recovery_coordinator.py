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


def test_checkpoint_allows_safe_resume_after_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-3")
    coordinator.execution_ledger.bind_external_id("req-3", "ext-3")
    coordinator.execution_ledger.mark_accepted("req-3")
    coordinator.execution_ledger.reconcile("req-3", executed=True)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-3", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc))
    )
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


def test_reserved_ledger_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reserved")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.unknown_request_ids == ("req-reserved",)


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


def test_accepted_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-accepted")
    coordinator.execution_ledger.bind_external_id("req-accepted", "external-1")
    coordinator.execution_ledger.mark_accepted("req-accepted")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_lifecycle_accepted_with_ledger_unknown_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_unknown("req-mismatch")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.ACCEPTED, now, "mismatch")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_pending_lifecycle_requires_reserved_ledger(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-pending")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, now, "pending")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION


def test_accepted_pair_requires_reconciliation_before_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-ok")
    coordinator.execution_ledger.bind_external_id("req-ok", "external-ok")
    coordinator.execution_ledger.mark_accepted("req-ok")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-ok", ExecutionLifecycleState.ACCEPTED, now, "accepted")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_reconciled_executed_pair_is_safe_to_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.bind_external_id("req-reconciled", "external-ok")
    coordinator.execution_ledger.mark_accepted("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=True)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.ACCEPTED, now, "executed")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_reconciled_not_executed_pair_is_safe_without_external_identity(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.reserve("req-not-executed")
    coordinator.execution_ledger.reconcile("req-not-executed", executed=False)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-not-executed", ExecutionLifecycleState.REJECTED, now, "not executed")
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_checkpoint_request_must_exist_in_persisted_execution_state(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(RuntimeCheckpoint("s1", 4, "missing-request", datetime.now(timezone.utc)))

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert "missing-request" in result.unknown_request_ids or "checkpoint" in result.message


def test_accepted_ledger_requires_external_identity_for_safe_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-accepted")
    coordinator.execution_ledger.mark_accepted("req-accepted")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-accepted", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc))
    )

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert "req-accepted" in result.message or "incompletos" in result.message


def test_reconciled_ledger_requires_external_identity_for_safe_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=True)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc))
    )

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
