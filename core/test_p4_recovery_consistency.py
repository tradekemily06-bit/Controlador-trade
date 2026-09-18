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
    assert result.message == "estado durável mudou durante a avaliação; retomada recusada até obter snapshot estável."
    assert any(status is ExecutionLedgerStatus.RESERVED for status in ledger.statuses().values())


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


def test_recovery_final_admission_check_can_ignore_only_current_request(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    ledger.reserve("current-request")
    lifecycle.put(
        __import__("execution.execution_lifecycle", fromlist=["ExecutionLifecycleRecord"]).ExecutionLifecycleRecord(
            "current-request",
            __import__("execution.execution_lifecycle", fromlist=["ExecutionLifecycleState"]).ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "admission in progress",
        )
    )
    coordinator = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )

    ignored = coordinator.assess(ignore_request_id="current-request")
    assert ignored.state is RecoveryState.FRESH
    assert ignored.can_resume is True

    ledger.reserve("other-uncertain-request")
    blocked = coordinator.assess(ignore_request_id="current-request")
    assert blocked.state is RecoveryState.REQUIRES_RECONCILIATION
    assert blocked.can_resume is False
    assert "other-uncertain-request" in blocked.message
