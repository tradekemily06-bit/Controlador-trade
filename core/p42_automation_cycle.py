from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.p41_controlled_automation import AutomationAuthorization


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
    """Turns a P41 authorization into an explicit, side-effect-free cycle request."""

    def request_cycle(
        self,
        authorization: AutomationAuthorization,
        *,
        cycle_id: str,
        requested_at: datetime,
    ) -> AutomationCycleResult:
        if not isinstance(authorization, AutomationAuthorization):
            return AutomationCycleResult(False, None, "invalid automation authorization")
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            return AutomationCycleResult(False, None, "invalid cycle id")
        if not isinstance(requested_at, datetime) or requested_at.tzinfo is None:
            return AutomationCycleResult(False, None, "requested_at must be timezone-aware")
        if not authorization.authorized:
            return AutomationCycleResult(False, None, "automation cycle not authorized")
        request = AutomationCycleRequest(cycle_id=cycle_id.strip(), requested_at=requested_at, mode="DEMO")
        return AutomationCycleResult(True, request, "automation cycle authorized")
