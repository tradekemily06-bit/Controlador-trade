from datetime import datetime, timezone

import pytest

from core.execution_intent import ExecutionIntent
from core.models import Signal
from core.p42_automation_cycle import AutomationCycleRequest
from core.p43_automation_admission import AutomationAdmissionResult
from core.p44_automation_intent_handoff import AutomationIntentHandoffBoundary
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from execution.ports import ExecutionMode
from core.demo_readiness import DemoReadinessReport


def make_intent(mode: ExecutionMode = ExecutionMode.DEMO) -> ExecutionIntent:
    return ExecutionIntent(
        request_id="req-44",
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=mode,
        created_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )


def make_admission(admitted: bool = True) -> AutomationAdmissionResult:
    request = AutomationCycleRequest(
        cycle_id="cycle-44",
        requested_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    ) if admitted else None
    return AutomationAdmissionResult(admitted, request, () if admitted else ("blocked",))


def test_approved_admission_and_demo_intent_create_handoff() -> None:
    result = AutomationIntentHandoffBoundary().handoff(
        make_admission(), intent=make_intent()
    )
    assert result.handed_off is True
    assert result.reasons == ()
    assert result.handoff is not None
    assert result.handoff.cycle_id == "cycle-44"
    assert result.handoff.intent.request_id == "req-44"


def test_blocked_admission_fails_closed() -> None:
    result = AutomationIntentHandoffBoundary().handoff(
        make_admission(False), intent=make_intent()
    )
    assert result.handed_off is False
    assert result.handoff is None
    assert "blocked" in result.reasons


def test_missing_or_invalid_intent_fails_closed() -> None:
    boundary = AutomationIntentHandoffBoundary()
    missing = boundary.handoff(make_admission(), intent=None)
    invalid = boundary.handoff(make_admission(), intent="bad")  # type: ignore[arg-type]
    assert missing.handed_off is False
    assert invalid.handed_off is False
    assert "execution intent is invalid" in missing.reasons
    assert "execution intent is invalid" in invalid.reasons


def test_real_intent_cannot_enter_handoff() -> None:
    with pytest.raises(ValueError):
        make_intent(ExecutionMode.REAL)


def test_invalid_admission_fails_closed() -> None:
    result = AutomationIntentHandoffBoundary().handoff(
        None, intent=make_intent()
    )
    assert result.handed_off is False
    assert result.handoff is None
    assert "automation admission result is invalid" in result.reasons


def test_handoff_result_is_immutable() -> None:
    result = AutomationIntentHandoffBoundary().handoff(
        make_admission(), intent=make_intent()
    )
    with pytest.raises(AttributeError):
        result.handed_off = False  # type: ignore[misc]
    assert result.handoff is not None
    with pytest.raises(AttributeError):
        result.handoff.cycle_id = "changed"  # type: ignore[misc]


def test_valid_result_is_independent_of_unrelated_risk_and_readiness_objects() -> None:
    readiness = DemoReadinessReport(True, ())
    risk = RiskBudgetAssessment(BudgetDecision.APPROVED, 1.0, 1, "ok")
    assert readiness.ready is True
    assert risk.decision is BudgetDecision.APPROVED
    result = AutomationIntentHandoffBoundary().handoff(
        make_admission(), intent=make_intent()
    )
    assert result.handed_off is True
