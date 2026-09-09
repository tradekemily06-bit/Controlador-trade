from datetime import datetime, timezone

import pytest

from audit.execution_audit import ExecutionAuditEvent, ExecutionAuditLog
from core.operational_safety_store import OperationalSafetyStore
from execution.execution_lifecycle import ExecutionLifecycleState


def event(state=ExecutionLifecycleState.PENDING, request_id="req-29"):
    return ExecutionAuditEvent(request_id, state, datetime(2026, 1, 1, tzinfo=timezone.utc), "evento")


def test_event_is_immutable_and_queryable():
    item = event()
    log = ExecutionAuditLog()
    log.append(item)
    assert log.events() == (item,)
    assert log.for_request("req-29") == (item,)
    with pytest.raises((AttributeError, TypeError)):
        item.message = "changed"


def test_invalid_event_fails_closed():
    with pytest.raises(ValueError):
        ExecutionAuditEvent("", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc), "evento")


def test_audit_log_does_not_expose_mutable_storage():
    log = ExecutionAuditLog()
    log.append(event())
    events = log.events()
    assert isinstance(events, tuple)
    with pytest.raises(AttributeError):
        events.append(event())


def test_execution_audit_is_restored_from_existing_safety_store(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    first = ExecutionAuditLog(store)
    first.append(event())
    first.append(event(ExecutionLifecycleState.ACCEPTED, "req-30"))

    restored = ExecutionAuditLog(OperationalSafetyStore(tmp_path / "safety.json"))
    assert restored.events() == first.events()
    assert restored.for_request("req-30")[0].state is ExecutionLifecycleState.ACCEPTED


def test_operational_safety_save_preserves_execution_audit(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    log = ExecutionAuditLog(store)
    log.append(event())

    from core.decision_audit import DecisionAudit
    from core.kill_switch import KillSwitch

    store.save(DecisionAudit(), KillSwitch())
    restored = ExecutionAuditLog(store)
    assert restored.events() == log.events()


def test_persisted_invalid_execution_state_fails_closed(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text(
        '{"audit": [], "kill_switch": {}, "execution_audit": '
        '[{"request_id":"req-29","state":"NOT_A_STATE","timestamp":"2026-01-01T00:00:00+00:00","message":"evento"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        ExecutionAuditLog(OperationalSafetyStore(path))
