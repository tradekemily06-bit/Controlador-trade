from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from core.execution_intent import ExecutionIntent
from core.p41_controlled_automation import AutomationCycle, AutomationDecision, AutomationPolicy, ControlledAutomationGate
from core.p42_automation_cycle import AutomationCycleOrchestrator, AutomationCycleResult
from core.p43_automation_admission import AutomationAdmission, AutomationAdmissionResult
from core.p44_automation_intent_handoff import AutomationIntentHandoffBoundary, AutomationIntentHandoffResult
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleBoundary, AutomationLifecycleState
from core.p40_risk_budget import RiskBudgetAssessment
from core.demo_readiness import DemoReadinessReport


@dataclass(frozen=True)
class ControlledAutomationResult:
    decision: AutomationDecision
    cycle: AutomationCycleResult
    admission: AutomationAdmissionResult
    handoff: AutomationIntentHandoffResult
    lifecycle: AutomationLifecycle
    execution: object | None
    reason: str


class ControlledAutomationRuntime:
    """Productive DEMO-only bridge for P41 -> P42 -> P43 -> P44 -> execution lifecycle.

    The bridge never enables REAL and never bypasses the existing execution
    admission/gateway. It only supplies the missing orchestration between the
    already validated boundaries.
    """

    def __init__(
        self,
        *,
        policy: AutomationPolicy,
        gate: ControlledAutomationGate | None = None,
        cycle_orchestrator: AutomationCycleOrchestrator | None = None,
        admission: AutomationAdmission | None = None,
        handoff: AutomationIntentHandoffBoundary | None = None,
        lifecycle: AutomationLifecycleBoundary | None = None,
    ) -> None:
        if not isinstance(policy, AutomationPolicy):
            raise ValueError("automation policy is required")
        self.policy = policy
        self.gate = gate or ControlledAutomationGate()
        self.cycle_orchestrator = cycle_orchestrator or AutomationCycleOrchestrator()
        self.admission = admission or AutomationAdmission()
        self.handoff = handoff or AutomationIntentHandoffBoundary()
        self.lifecycle = lifecycle or AutomationLifecycleBoundary()

    def prepare(
        self,
        *,
        cycle_id: str,
        requested_at: datetime,
        readiness: DemoReadinessReport,
        risk_budget: RiskBudgetAssessment,
        intent: ExecutionIntent | None,
        last_cycle_at: datetime | None = None,
    ) -> ControlledAutomationResult:
        if not isinstance(requested_at, datetime) or requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        cycle = AutomationCycle(cycle_id, requested_at)
        decision = self.gate.evaluate(self.policy, cycle, last_cycle_at=last_cycle_at)
        cycle_result = self.cycle_orchestrator.request_cycle(decision, requested_at=requested_at)
        if not cycle_result.authorized:
            return ControlledAutomationResult(
                decision, cycle_result, AutomationAdmissionResult(False, None, (cycle_result.reason,)),
                AutomationIntentHandoffResult(False, None, (cycle_result.reason,)),
                AutomationLifecycle(cycle_id, AutomationLifecycleState.BLOCKED), None, cycle_result.reason,
            )

        admission = self.admission.admit(cycle_result.request, readiness=readiness, risk_budget=risk_budget)
        if not admission.admitted:
            return ControlledAutomationResult(
                decision, cycle_result, admission,
                AutomationIntentHandoffResult(False, None, admission.reasons),
                AutomationLifecycle(cycle_id, AutomationLifecycleState.BLOCKED), None,
                "; ".join(admission.reasons),
            )

        lifecycle = AutomationLifecycle(cycle_id, AutomationLifecycleState.CREATED)
        lifecycle = self.lifecycle.transition(lifecycle, AutomationLifecycleState.ADMITTED)
        handoff = self.handoff.handoff(admission, intent=intent)
        if not handoff.handed_off:
            lifecycle = self.lifecycle.transition(lifecycle, AutomationLifecycleState.BLOCKED)
            return ControlledAutomationResult(decision, cycle_result, admission, handoff, lifecycle, None, "; ".join(handoff.reasons))

        lifecycle = self.lifecycle.transition(lifecycle, AutomationLifecycleState.DISPATCHED)
        return ControlledAutomationResult(decision, cycle_result, admission, handoff, lifecycle, None, "ready for gateway dispatch")

    def complete(self, prepared: ControlledAutomationResult, execution) -> ControlledAutomationResult:
        if not isinstance(prepared, ControlledAutomationResult):
            raise ValueError("prepared automation result is invalid")
        if prepared.lifecycle.state is not AutomationLifecycleState.DISPATCHED:
            raise ValueError("only DISPATCHED automation can be completed")
        accepted = bool(getattr(execution, "accepted", False))
        target = AutomationLifecycleState.COMPLETED if accepted else AutomationLifecycleState.BLOCKED
        lifecycle = self.lifecycle.transition(prepared.lifecycle, target)
        return ControlledAutomationResult(
            prepared.decision, prepared.cycle, prepared.admission, prepared.handoff,
            lifecycle, execution, "execution completed" if accepted else "execution blocked",
        )
