from datetime import datetime, timezone

from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


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
        ExecutionLifecycleRecord(
            "current-request",
            ExecutionLifecycleState.PENDING,
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
    assert blocked.message == "ledger RESERVED/UNKNOWN requer reconciliação"


def test_terminal_lifecycle_repair_waits_for_request_lock(tmp_path):
    from threading import Event, Thread

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    coordinator = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    ledger.reserve("repair-race")
    ledger.mark_accepted("repair-race")

    started = Event()
    finished = Event()
    result = {}

    def repair():
        started.set()
        result["record"] = coordinator.reconcile_terminal_lifecycle(
            "repair-race",
            updated_at=datetime.now(timezone.utc),
            message="repair",
        )
        finished.set()

    with ledger.request_execution_lock("repair-race"):
        worker = Thread(target=repair)
        worker.start()
        assert started.wait(timeout=2)
        assert not finished.wait(timeout=0.2)

    worker.join(timeout=2)
    assert finished.is_set()
    assert result["record"].state is ExecutionLifecycleState.ACCEPTED
    assert lifecycle.get("repair-race").state is ExecutionLifecycleState.ACCEPTED
