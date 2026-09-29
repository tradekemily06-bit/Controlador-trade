from datetime import datetime, timezone

import pytest

from core.operation_memory import OperationMemory
from core.operation_lineage import OperationLineage, OperationLineageStore
from core.operation_context_store import OperationContextStore
from core.decision_snapshot import DecisionSnapshot
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
        lineage_store=OperationLineageStore(tmp_path / "lineage.json"),
        operation_context_store=OperationContextStore(tmp_path / "context.json"),
    )


def test_fresh_session_is_safe(tmp_path):
    result = make_coordinator(tmp_path).assess()
    assert result.state is RecoveryState.FRESH
    assert result.can_resume is True


def test_checkpoint_without_identity_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.checkpoint_store.save(RuntimeCheckpoint("s1", 3, "req-3", datetime.now(timezone.utc)))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
    assert result.checkpoint.last_cycle == 3


def test_checkpoint_with_matching_identity_allows_safe_resume(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lineage_store.put(OperationLineage("decision-3", "cycle-3", "req-3", updated_at=now))
    coordinator.operation_context_store.put("req-3", DecisionSnapshot(
        signal="COMPRA", analysis_score=80, confirmed=True, quality_score=80,
        quality_level="HIGH", actionable=True, decision="EXECUTAR",
        decision_reason="test", market_context=None, market_direction=None,
        market_score=None, operational_state_available=True, trades_today=0,
        consecutive_losses=0, symbol="EURUSD", timeframe="5m",
        decision_id="decision-3", cycle_id="cycle-3", request_id="req-3",
    ))
    coordinator.checkpoint_store.save(RuntimeCheckpoint(
        "s1", 3, "req-3", now, last_decision_id="decision-3", last_cycle_id="cycle-3"
    ))
    result = coordinator.assess()
    assert result.state is RecoveryState.SAFE_TO_RESUME
    assert result.can_resume is True
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


def test_checkpoint_identity_mismatch_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    now = datetime.now(timezone.utc)
    coordinator.lineage_store.put(OperationLineage("decision-1", "cycle-1", "req-1", updated_at=now))
    coordinator.operation_context_store.put("req-1", DecisionSnapshot(
        signal="COMPRA", analysis_score=80, confirmed=True, quality_score=80,
        quality_level="HIGH", actionable=True, decision="EXECUTAR",
        decision_reason="test", market_context=None, market_direction=None,
        market_score=None, operational_state_available=True, trades_today=0,
        consecutive_losses=0, symbol="EURUSD", timeframe="5m",
        decision_id="decision-1", cycle_id="cycle-1", request_id="req-1",
    ))
    coordinator.checkpoint_store.save(RuntimeCheckpoint(
        "s1", 1, "req-1", now, last_decision_id="wrong", last_cycle_id="cycle-1"
    ))
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False


def test_missing_lineage_for_persisted_lifecycle_requires_reconciliation(tmp_path):
    coordinator = make_coordinator(tmp_path)
    coordinator.lifecycle_store.put(
        ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, datetime.now(timezone.utc))
    )
    result = coordinator.assess()
    assert result.state is RecoveryState.REQUIRES_RECONCILIATION
    assert result.can_resume is False
