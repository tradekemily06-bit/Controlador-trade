from __future__ import annotations

from dataclasses import dataclass

from core.execution_intent import ExecutionIntent
from core.p43_automation_admission import AutomationAdmissionResult


@dataclass(frozen=True)
class AutomationIntentHandoff:
    """Immutable handoff artifact; it never invokes an execution adapter."""

    cycle_id: str
    intent: ExecutionIntent


@dataclass(frozen=True)
class AutomationIntentHandoffResult:
    handed_off: bool
    handoff: AutomationIntentHandoff | None
    reasons: tuple[str, ...]


class AutomationIntentHandoffBoundary:
    """Connects approved automation admission to a validated DEMO intent only."""

    def handoff(
        self,
        admission: AutomationAdmissionResult | None,
        *,
        intent: ExecutionIntent | None,
    ) -> AutomationIntentHandoffResult:
        reasons: list[str] = []
        if not isinstance(admission, AutomationAdmissionResult):
            reasons.append("automation admission result is invalid")
        elif not admission.admitted:
            reasons.extend(admission.reasons or ("automation admission blocked",))
        elif admission.request is None:
            reasons.append("approved automation admission has no request")
        elif admission.request.mode != "DEMO":
            reasons.append("only DEMO cycle requests can enter automation handoff")

        if not isinstance(intent, ExecutionIntent):
            reasons.append("execution intent is invalid")
        elif intent.mode.value != "DEMO":
            reasons.append("only DEMO intent can enter automation handoff")

        if reasons:
            return AutomationIntentHandoffResult(False, None, tuple(reasons))

        assert admission is not None and admission.request is not None and intent is not None
        return AutomationIntentHandoffResult(
            True,
            AutomationIntentHandoff(
                cycle_id=admission.request.cycle_id,
                intent=intent,
            ),
            (),
        )
