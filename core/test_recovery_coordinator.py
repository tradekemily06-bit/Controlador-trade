from datetime import datetime, timezone

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def _coordinator(tmp_path):
    return RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
        memory=OperationMemory(),
    )


def test_recovery_detects_ledger_accepted_with_pending_lifecycle(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.record("req-1")
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ("req-1",)


def test_recovery_detects_ledger_unknown_without_lifecycle(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-2")
    coordinator.execution_ledger.mark_unknown("req-2")
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ("req-2",)


def test_recovery_accepts_clean_state(tmp_path):
    coordinator = _coordinator(tmp_path)
    assert coordinator.assess().state is RecoveryState.FRESH


def test_recovery_detects_terminal_ledger_without_lifecycle(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-3")
    coordinator.execution_ledger.mark_accepted("req-3")
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ("req-3",)


def test_recovery_detects_lifecycle_without_ledger(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-4", ExecutionLifecycleState.PENDING, now))
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ("req-4",)


def test_recovery_allows_pending_lifecycle_with_reserved_ledger(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.reserve("req-pending")
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ()
    assert assessment.pending_request_ids == ("req-pending",)


def test_recovery_accepts_reconciled_executed_with_terminal_lifecycle(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.bind_external_id("req-reconciled", "broker-1")
    coordinator.execution_ledger.mark_accepted("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=True, external_id="broker-1")
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-reconciled", ExecutionLifecycleState.ACCEPTED, now))
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.FRESH
    assert assessment.can_resume is True
    assert assessment.inconsistent_request_ids == ()


def test_recovery_checkpoint_never_overrides_pending_execution_state(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-crash", ExecutionLifecycleState.PENDING, now)
    )
    coordinator.execution_ledger.reserve("req-crash")
    coordinator.checkpoint_store.save(
        __import__("core.runtime_checkpoint", fromlist=["RuntimeCheckpoint"]).RuntimeCheckpoint(
            "session-1", 9, "req-crash", now
        )
    )
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False
    assert assessment.pending_request_ids == ("req-crash",)



def test_recovery_rejects_accepted_ledger_without_external_identity(tmp_path):
    coordinator = _coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-no-id", ExecutionLifecycleState.ACCEPTED, now)
    )
    coordinator.execution_ledger.reserve("req-no-id")
    coordinator.execution_ledger.mark_accepted("req-no-id")
    assessment = coordinator.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.inconsistent_request_ids == ("req-no-id",)
