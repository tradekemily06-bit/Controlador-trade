from datetime import datetime, timezone

import pytest

from audit.execution_audit import ExecutionAuditEvent, ExecutionAuditLog
from execution.execution_lifecycle import ExecutionLifecycleState


def event(state=ExecutionLifecycleState.PENDING):
    return ExecutionAuditEvent("req-29", state, datetime(2026, 1, 1, tzinfo=timezone.utc), "evento")


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
