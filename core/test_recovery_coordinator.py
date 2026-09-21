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


def test_repair_terminal_lifecycle_projection_from_ledger(tmp_path):
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    memory = OperationMemory()
    ledger.reserve("repair-1")
    ledger.mark_accepted("repair-1", external_id="broker-repair-1")
    lifecycle.put(ExecutionLifecycleRecord("repair-1", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)))
    coordinator = RecoveryCoordinator(checkpoint_store=checkpoint, lifecycle_store=lifecycle, execution_ledger=ledger, memory=memory)
    coordinator.repair_terminal_lifecycle_projection("repair-1")
    assert lifecycle.get("repair-1").state is ExecutionLifecycleState.ACCEPTED


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


def test_lifecycle_and_ledger_mismatch_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.execution_ledger.record("req-1")
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert "inconsistentes" in result.message


def test_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.record("orphaned")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert "ledger sem lifecycle" in result.message


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


def test_terminal_ledger_without_external_id_requires_reconciliation(tmp_path):
    (tmp_path / "ledger.json").write_text(
        '{"accepted-without-id": {"status": "ACCEPTED", "external_id_required": true}}',
        encoding="utf-8",
    )
    coordinator = make_coordinator(tmp_path)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord(
            "accepted-without-id",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
        )
    )

    assessment = coordinator.assess()

    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False


def test_demo_terminal_record_does_not_block_recovery_for_missing_external_id(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.record("demo-1")
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord(
            "demo-1",
            ExecutionLifecycleState.ACCEPTED,
            datetime.now(timezone.utc),
        )
    )

    assessment = coordinator.assess()

    assert assessment.state is RecoveryState.FRESH
