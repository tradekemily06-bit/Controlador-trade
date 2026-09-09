from __future__ import annotations

from dataclasses import dataclass

from core.demo_readiness import DemoReadinessReport
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from core.p42_automation_cycle import AutomationCycleRequest


@dataclass(frozen=True)
class AutomationAdmissionResult:
    admitted: bool
    request: AutomationCycleRequest | None
    reasons: tuple[str, ...]


class AutomationAdmission:
    """Read-only admission boundary for an already authorized DEMO cycle."""

    def admit(
        self,
        request: AutomationCycleRequest | None,
        *,
        readiness: DemoReadinessReport,
        risk_budget: RiskBudgetAssessment,
    ) -> AutomationAdmissionResult:
        reasons: list[str] = []
        if not isinstance(request, AutomationCycleRequest):
            reasons.append("automation cycle request is invalid")
        if not isinstance(readiness, DemoReadinessReport):
            reasons.append("demo readiness report is invalid")
        elif not readiness.ready:
            reasons.extend(readiness.reasons or ("demo readiness blocked",))
        if not isinstance(risk_budget, RiskBudgetAssessment):
            reasons.append("risk budget assessment is invalid")
        elif risk_budget.decision is not BudgetDecision.APPROVED:
            reasons.append(risk_budget.reason)
        if reasons:
            return AutomationAdmissionResult(False, None, tuple(reasons))
        assert request is not None
        return AutomationAdmissionResult(True, request, ())
