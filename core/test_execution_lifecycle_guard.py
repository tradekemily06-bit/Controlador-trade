from datetime import datetime, timezone

from core.execution_lifecycle_guard import ExecutionLifecycleGuard
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState


def record(state):
    return ExecutionLifecycleRecord("req", state, datetime(2026, 1, 1, tzinfo=timezone.utc), "test")


def test_new_cycle_must_start_pending():
    guard = ExecutionLifecycleGuard()
    assert guard.validate(None, ExecutionLifecycleState.PENDING).allowed
    assert not guard.validate(None, ExecutionLifecycleState.ACCEPTED).allowed


def test_pending_can_resolve_once():
    guard = ExecutionLifecycleGuard()
    assert guard.validate(record(ExecutionLifecycleState.PENDING), ExecutionLifecycleState.ACCEPTED).allowed
    assert guard.validate(record(ExecutionLifecycleState.PENDING), ExecutionLifecycleState.REJECTED).allowed
    assert guard.validate(record(ExecutionLifecycleState.PENDING), ExecutionLifecycleState.UNKNOWN).allowed


def test_terminal_states_cannot_be_replayed():
    guard = ExecutionLifecycleGuard()
    for state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED, ExecutionLifecycleState.UNKNOWN):
        assert not guard.validate(record(state), ExecutionLifecycleState.PENDING).allowed


def test_unknown_requires_explicit_reconciliation():
    result = ExecutionLifecycleGuard().validate(record(ExecutionLifecycleState.UNKNOWN), ExecutionLifecycleState.ACCEPTED)
    assert not result.allowed
    assert "reconciliação" in result.reason
