from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.p41_controlled_automation import AutomationDecision


@dataclass(frozen=True)
class AutomationCycleRequest:
    cycle_id: str
    requested_at: datetime
    mode: str = "DEMO"


@dataclass(frozen=True)
class AutomationCycleResult:
    authorized: bool
    request: AutomationCycleRequest | None
    reason: str


class AutomationCycleOrchestrator:
    """Turns a P41 decision into an explicit, side-effect-free cycle request."""

    def request_cycle(
        self,
        decision: AutomationDecision,
        *,
        requested_at: datetime,
    ) -> AutomationCycleResult:
        if not isinstance(decision, AutomationDecision):
            return AutomationCycleResult(False, None, "invalid automation decision")
        if not isinstance(requested_at, datetime) or requested_at.tzinfo is None or requested_at.utcoffset() is None:
            return AutomationCycleResult(False, None, "requested_at must be timezone-aware")
        if not decision.allowed:
            return AutomationCycleResult(False, None, "automation cycle not authorized")
        request = AutomationCycleRequest(cycle_id=decision.cycle_id, requested_at=requested_at, mode="DEMO")
        return AutomationCycleResult(True, request, "automation cycle authorized")
