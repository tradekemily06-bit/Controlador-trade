from datetime import datetime, timezone

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore


def test_recovery_refuses_mixed_cross_store_snapshot(tmp_path, monkeypatch):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    coordinator = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )

    original_statuses = ledger.statuses
    calls = {"count": 0}

    def mutate_between_reads():
        calls["count"] += 1
        snapshot = original_statuses()
        if calls["count"] % 2 == 1:
            ledger.reserve(f"racing-recovery-{calls["count"]}")
        return snapshot

    monkeypatch.setattr(ledger, "statuses", mutate_between_reads)

    result = coordinator.assess()

    assert calls["count"] >= 2
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.checkpoint is None
    assert result.message == "ledger RESERVED/UNKNOWN requer reconciliação"
    assert ledger.status("racing-recovery") is ExecutionLedgerStatus.RESERVED


def test_recovery_retries_after_transient_cross_store_change(tmp_path, monkeypatch):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    coordinator = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )

    original_statuses = ledger.statuses
    calls = {"count": 0}

    def mutate_once():
        calls["count"] += 1
        snapshot = original_statuses()
        if calls["count"] == 1:
            ledger.reserve("transient-recovery")
        return snapshot

    monkeypatch.setattr(ledger, "statuses", mutate_once)

    result = coordinator.assess()

    assert calls["count"] >= 2
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert ledger.status("transient-recovery") is ExecutionLedgerStatus.RESERVED
