from dataclasses import FrozenInstanceError

import pytest

from core.demo_readiness import DemoReadinessReport
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from core.p42_automation_cycle import AutomationCycleRequest
from core.p43_automation_admission import AutomationAdmission


def request():
    from datetime import datetime, timezone
    return AutomationCycleRequest("cycle-1", datetime(2026, 1, 1, tzinfo=timezone.utc))


def approved_readiness():
    return DemoReadinessReport(True, ())


def approved_budget():
    return RiskBudgetAssessment(BudgetDecision.APPROVED, 10.0, 1, "risk budget satisfied")


def test_admits_only_when_all_boundaries_approve():
    result = AutomationAdmission().admit(request(), readiness=approved_readiness(), risk_budget=approved_budget())
    assert result.admitted is True
    assert result.request == request()
    assert result.reasons == ()


def test_blocks_when_p30_readiness_blocks():
    result = AutomationAdmission().admit(
        request(),
        readiness=DemoReadinessReport(False, ("kill switch active",)),
        risk_budget=approved_budget(),
    )
    assert result.admitted is False
    assert result.request is None
    assert "kill switch active" in result.reasons


def test_blocks_when_p40_budget_blocks():
    result = AutomationAdmission().admit(
        request(),
        readiness=approved_readiness(),
        risk_budget=RiskBudgetAssessment(BudgetDecision.BLOCKED, 101.0, 1, "daily loss budget exceeded"),
    )
    assert result.admitted is False
    assert result.request is None
    assert "daily loss budget exceeded" in result.reasons


def test_invalid_inputs_fail_closed():
    result = AutomationAdmission().admit(None, readiness=object(), risk_budget=object())
    assert result.admitted is False
    assert result.request is None
    assert len(result.reasons) == 3


def test_result_is_immutable():
    result = AutomationAdmission().admit(request(), readiness=approved_readiness(), risk_budget=approved_budget())
    with pytest.raises(FrozenInstanceError):
        result.admitted = False
