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
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
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
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION


def test_ledger_unknown_without_lifecycle_is_reconciliation_required(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-ledger")
    coordinator.execution_ledger.mark_unknown("req-ledger")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.unknown_request_ids == ("req-ledger",)


def test_ledger_terminal_without_lifecycle_is_reconciliation_required(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-ledger")
    coordinator.execution_ledger.mark_rejected("req-ledger")
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION


def test_terminal_state_mismatch_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.reserve("req-mismatch")
    coordinator.execution_ledger.mark_rejected("req-mismatch")
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-mismatch", ExecutionLifecycleState.ACCEPTED, now))

    result = coordinator.assess()

    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert "divergentes" in result.message


def test_reconciled_ledger_without_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-reconciled")
    coordinator.execution_ledger.reconcile("req-reconciled", executed=True, external_id="broker-reconciled")

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


def test_persistence_access_error_fails_closed(tmp_path, monkeypatch):
    coordinator = make_coordinator(tmp_path)

    def unavailable_snapshot():
        raise OSError("permission denied")

    monkeypatch.setattr(coordinator.lifecycle_store, "snapshot", unavailable_snapshot)

    result = coordinator.assess()

    assert result.state is RecoveryState.INVALID
    assert result.can_resume is False


def test_terminal_ledger_divergence_can_be_explicitly_repaired(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-ledger")
    coordinator.execution_ledger.bind_external_id("req-ledger", "broker-123")
    coordinator.execution_ledger.mark_accepted("req-ledger", external_id="broker-123")

    assert coordinator.assess().state is RecoveryState.REQUIRES_RECONCILIATION
    repaired = coordinator.repair_terminal_divergence()
    assert repaired == ("req-ledger",)
    result = coordinator.assess()
    assert result.state is RecoveryState.FRESH
    assert coordinator.lifecycle_store.get("req-ledger").state is ExecutionLifecycleState.ACCEPTED


def test_terminal_repair_refuses_conflicting_lifecycle(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-ledger", ExecutionLifecycleState.PENDING, now))
    coordinator.execution_ledger.reserve("req-ledger")
    coordinator.execution_ledger.mark_rejected("req-ledger")
    coordinator.lifecycle_store.put(ExecutionLifecycleRecord("req-ledger", ExecutionLifecycleState.REJECTED, now))
    assert coordinator.repair_terminal_divergence() == ()


def test_accepted_ledger_without_external_id_cannot_be_repaired(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.execution_ledger.reserve("req-ledger")
    # The public ledger transition requires an external_id, so emulate a
    # malformed persisted state by replacing the file directly.
    (tmp_path / "ledger.json").write_text(
        '{"states":{"req-ledger":"ACCEPTED"},"external_ids":{}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="external_id"):
        coordinator.repair_terminal_divergence()
