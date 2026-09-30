from datetime import datetime, timezone

import pytest

from core.demo_readiness import DemoReadinessReport
from core.execution_intent import ExecutionIntent
from core.models import Signal
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from core.p41_controlled_automation import AutomationCycle, AutomationPolicy, AutomationLifecycleState
from execution.ports import ExecutionMode
from integration.controlled_automation_service import ControlledAutomationService


NOW = datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)


def readiness(ready=True):
    return DemoReadinessReport(ready=ready, reasons=() if ready else ("blocked",))


def budget(approved=True):
    return RiskBudgetAssessment(
        decision=BudgetDecision.APPROVED if approved else BudgetDecision.BLOCKED,
        reason="approved" if approved else "budget blocked",
    )


def intent(cycle_id="cycle-integrated"):
    return ExecutionIntent(
        request_id="req-integrated",
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        created_at=NOW,
        cycle_id=cycle_id,
    )


def test_controlled_automation_composes_p41_to_p45_without_execution():
    service = ControlledAutomationService()
    result = service.admit(
        policy=AutomationPolicy(enabled=True, minimum_interval_seconds=60),
        cycle=AutomationCycle("cycle-integrated", NOW),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent(),
    )

    assert result.admission.admitted is True
    assert result.handoff is not None and result.handoff.handed_off is True
    assert result.audit is not None and result.audit.cycle_id == "cycle-integrated"
    assert result.lifecycle.state is AutomationLifecycleState.ADMITTED


def test_cycle_identity_mismatch_fails_closed_before_audit():
    service = ControlledAutomationService()
    result = service.admit(
        policy=AutomationPolicy(enabled=True, minimum_interval_seconds=60),
        cycle=AutomationCycle("cycle-integrated", NOW),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent("different-cycle"),
    )

    assert result.handoff is not None
    assert result.handoff.handed_off is False
    assert result.audit is None
    assert result.lifecycle.state is AutomationLifecycleState.BLOCKED


def test_lifecycle_cannot_be_reused_after_completion():
    service = ControlledAutomationService()
    result = service.admit(
        policy=AutomationPolicy(enabled=True, minimum_interval_seconds=60),
        cycle=AutomationCycle("cycle-terminal", NOW),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent("cycle-terminal"),
    )
    assert result.lifecycle.state is AutomationLifecycleState.ADMITTED

    service.mark_dispatched("cycle-terminal")
    service.complete("cycle-terminal")

    with pytest.raises(ValueError, match="terminal automation lifecycle"):
        service.block("cycle-terminal")


def test_blocked_admission_never_creates_execution_handoff():
    service = ControlledAutomationService()
    result = service.admit(
        policy=AutomationPolicy(enabled=False, minimum_interval_seconds=60),
        cycle=AutomationCycle("cycle-blocked", NOW),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent("cycle-blocked"),
    )

    assert result.lifecycle.state is AutomationLifecycleState.BLOCKED
    assert result.handoff is None
    assert result.audit is None
