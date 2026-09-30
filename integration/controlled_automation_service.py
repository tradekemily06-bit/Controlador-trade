from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.demo_readiness import DemoReadinessReport
from core.execution_intent import ExecutionIntent
from core.p40_risk_budget import RiskBudgetAssessment
from core.p41_controlled_automation import AutomationCycle, AutomationDecision, AutomationPolicy, ControlledAutomationGate
from core.p42_automation_cycle import AutomationCycleOrchestrator, AutomationCycleRequest
from core.p43_automation_admission import AutomationAdmission, AutomationAdmissionResult
from core.p44_automation_intent_handoff import AutomationIntentHandoff, AutomationIntentHandoffBoundary, AutomationIntentHandoffResult
from core.p45_automation_audit import AutomationAuditRecord, AutomationAuditBoundary
from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleBoundary, AutomationLifecycleState
from core.p139_post_demo_learning import PostDemoLearningBoundary, PostDemoLearningResult


@dataclass(frozen=True)
class ControlledAutomationAdmission:
    """Single application-level composition of P41-P46; it never executes."""

    decision: AutomationDecision
    request: AutomationCycleRequest | None
    admission: AutomationAdmissionResult
    handoff: AutomationIntentHandoffResult | None
    audit: AutomationAuditRecord | None
    lifecycle: AutomationLifecycle


class ControlledAutomationService:
    """Keep the automation lifecycle as one integrated application boundary.

    P41-P45 remain pure/read-only. P46 state is held as immutable snapshots in
    this service. Actual broker dispatch remains owned by the existing
    execution gateway and is never called here.
    """

    def __init__(self) -> None:
        self._gate = ControlledAutomationGate()
        self._cycle_orchestrator = AutomationCycleOrchestrator()
        self._admission = AutomationAdmission()
        self._handoff = AutomationIntentHandoffBoundary()
        self._audit = AutomationAuditBoundary()
        self._lifecycle = AutomationLifecycleBoundary()
        self._cycles: dict[str, AutomationLifecycle] = {}

    def admit(
        self,
        *,
        policy: AutomationPolicy,
        cycle: AutomationCycle,
        readiness: DemoReadinessReport,
        risk_budget: RiskBudgetAssessment,
        intent: ExecutionIntent,
        last_cycle_at: datetime | None = None,
    ) -> ControlledAutomationAdmission:
        decision = self._gate.evaluate(policy, cycle, last_cycle_at=last_cycle_at)
        lifecycle = AutomationLifecycle(cycle.cycle_id, AutomationLifecycleState.CREATED)
        request_result = self._cycle_orchestrator.request_cycle(
            decision,
            requested_at=cycle.requested_at,
        )
        request = request_result.request
        admission = self._admission.admit(
            request,
            readiness=readiness,
            risk_budget=risk_budget,
        )

        if not request_result.authorized or not admission.admitted:
            lifecycle = self._lifecycle.transition(lifecycle, AutomationLifecycleState.BLOCKED)
            self._cycles[cycle.cycle_id] = lifecycle
            return ControlledAutomationAdmission(
                decision=decision,
                request=request,
                admission=admission,
                handoff=None,
                audit=None,
                lifecycle=lifecycle,
            )

        lifecycle = self._lifecycle.transition(lifecycle, AutomationLifecycleState.ADMITTED)
        handoff = self._handoff.handoff(admission, intent=intent)
        if not handoff.handed_off:
            lifecycle = self._lifecycle.transition(lifecycle, AutomationLifecycleState.BLOCKED)
            self._cycles[cycle.cycle_id] = lifecycle
            return ControlledAutomationAdmission(
                decision=decision,
                request=request,
                admission=admission,
                handoff=handoff,
                audit=None,
                lifecycle=lifecycle,
            )

        audit = self._audit.record(handoff)
        self._cycles[cycle.cycle_id] = lifecycle
        return ControlledAutomationAdmission(
            decision=decision,
            request=request,
            admission=admission,
            handoff=handoff,
            audit=audit,
            lifecycle=lifecycle,
        )

    def mark_dispatched(self, cycle_id: str) -> AutomationLifecycle:
        current = self._current(cycle_id)
        updated = self._lifecycle.transition(current, AutomationLifecycleState.DISPATCHED)
        self._cycles[cycle_id] = updated
        return updated

    def complete(self, cycle_id: str) -> AutomationLifecycle:
        current = self._current(cycle_id)
        updated = self._lifecycle.transition(current, AutomationLifecycleState.COMPLETED)
        self._cycles[cycle_id] = updated
        return updated

    def block(self, cycle_id: str) -> AutomationLifecycle:
        current = self._current(cycle_id)
        if current.state.value in {"COMPLETED", "BLOCKED"}:
            raise ValueError("terminal automation lifecycle cannot be reused")
        updated = self._lifecycle.transition(current, AutomationLifecycleState.BLOCKED)
        self._cycles[cycle_id] = updated
        return updated

    def lifecycle(self, cycle_id: str) -> AutomationLifecycle:
        return self._current(cycle_id)

    def post_demo_learning(self, **kwargs) -> PostDemoLearningResult:
        """Continue a terminal cycle through the existing P47-P128 learning boundary."""
        return PostDemoLearningBoundary().process(**kwargs)

    def _current(self, cycle_id: str) -> AutomationLifecycle:
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id is required")
        current = self._cycles.get(cycle_id)
        if current is None:
            raise ValueError("automation cycle not found")
        return current
