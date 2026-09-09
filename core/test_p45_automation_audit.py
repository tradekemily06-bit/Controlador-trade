from datetime import datetime, timezone

import pytest

from core.execution_intent import ExecutionIntent
from core.models import Signal
from core.p42_automation_cycle import AutomationCycleRequest
from core.p43_automation_admission import AutomationAdmissionResult
from core.p44_automation_intent_handoff import AutomationIntentHandoffBoundary
from core.p45_automation_audit import AutomationAuditBoundary
from execution.ports import ExecutionMode


def make_handoff():
    admission = AutomationAdmissionResult(
        True,
        AutomationCycleRequest("cycle-45", datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)),
        (),
    )
    intent = ExecutionIntent(
        request_id="req-45", symbol="EURUSD", signal=Signal.COMPRA,
        amount=10.0, duration_seconds=60, mode=ExecutionMode.DEMO,
        created_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )
    return AutomationIntentHandoffBoundary().handoff(admission, intent=intent)


def test_records_factual_handoff() -> None:
    record = AutomationAuditBoundary().record(make_handoff())
    assert record.cycle_id == "cycle-45"
    assert record.request_id == "req-45"
    assert record.symbol == "EURUSD"
    assert record.direction == Signal.COMPRA.value
    assert record.mode == "DEMO"


def test_rejects_unapproved_handoff() -> None:
    with pytest.raises(ValueError):
        AutomationAuditBoundary().record(None)


def test_record_is_immutable() -> None:
    record = AutomationAuditBoundary().record(make_handoff())
    with pytest.raises(AttributeError):
        record.cycle_id = "changed"  # type: ignore[misc]


def test_audit_does_not_claim_execution_outcome() -> None:
    record = AutomationAuditBoundary().record(make_handoff())
    assert not hasattr(record, "profit")
    assert not hasattr(record, "execution_status")
    assert not hasattr(record, "result")
