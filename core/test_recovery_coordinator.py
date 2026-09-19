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
