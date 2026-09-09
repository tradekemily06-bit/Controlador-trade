from datetime import datetime, timezone

import pytest

from core.operation_memory import OperationMemory
from core.p21_observability import HealthState, RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def build(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    memory = OperationMemory()
    recovery = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=memory,
    )
    monitor = RuntimeHealthMonitor(
        ledger=ledger,
        lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
    )
    return monitor, lifecycle, ledger


def test_fresh_runtime_is_healthy(tmp_path):
    monitor, _, _ = build(tmp_path)
    health = monitor.assess()
    assert health.state is HealthState.HEALTHY
    assert health.recovery_state is RecoveryState.FRESH


def test_pending_runtime_requires_attention(tmp_path):
    monitor, lifecycle, _ = build(tmp_path)
    lifecycle.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)))
    health = monitor.assess()
    assert health.state is HealthState.ATTENTION
    assert health.pending_executions == 1


def test_unknown_runtime_is_blocked(tmp_path):
    monitor, lifecycle, _ = build(tmp_path)
    lifecycle.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc)))
    health = monitor.assess()
    assert health.state is HealthState.BLOCKED
    assert health.unknown_executions == 1


def test_accepted_without_ledger_requires_reconciliation(tmp_path):
    monitor, lifecycle, _ = build(tmp_path)
    lifecycle.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc)))
    health = monitor.assess()
    assert health.state is HealthState.ATTENTION
    assert health.recovery_state is RecoveryState.REQUIRES_RECONCILIATION


def test_invalid_dependency_is_rejected(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    checkpoint = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    memory = OperationMemory()
    recovery = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=memory,
    )
    with pytest.raises(ValueError):
        RuntimeHealthMonitor(ledger=ledger, lifecycle=lifecycle, checkpoint_store=object(), recovery=recovery)
