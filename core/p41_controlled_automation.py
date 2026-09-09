from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math


@dataclass(frozen=True)
class AutomationPolicy:
    enabled: bool
    minimum_interval_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")
        if (
            isinstance(self.minimum_interval_seconds, bool)
            or not isinstance(self.minimum_interval_seconds, (int, float))
            or not math.isfinite(float(self.minimum_interval_seconds))
            or self.minimum_interval_seconds < 0
        ):
            raise ValueError("minimum_interval_seconds must be finite and non-negative")


@dataclass(frozen=True)
class AutomationCycle:
    cycle_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.cycle_id, str) or not self.cycle_id.strip():
            raise ValueError("cycle_id must be non-empty")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")


@dataclass(frozen=True)
class AutomationDecision:
    allowed: bool
    reason: str
    cycle_id: str


class ControlledAutomationGate:
    """Read-only boundary for controlled cycle cadence; never executes work."""

    def evaluate(
        self,
        policy: AutomationPolicy,
        cycle: AutomationCycle,
        *,
        last_cycle_at: datetime | None = None,
    ) -> AutomationDecision:
        if not isinstance(policy, AutomationPolicy):
            raise ValueError("policy is invalid")
        if not isinstance(cycle, AutomationCycle):
            raise ValueError("cycle is invalid")
        if last_cycle_at is not None:
            if not isinstance(last_cycle_at, datetime):
                raise ValueError("last_cycle_at is invalid")
            if last_cycle_at.tzinfo is None or last_cycle_at.utcoffset() is None:
                raise ValueError("last_cycle_at must be timezone-aware")
            if cycle.requested_at < last_cycle_at:
                return AutomationDecision(False, "cycle timestamp precedes last cycle", cycle.cycle_id)

        if not policy.enabled:
            return AutomationDecision(False, "automation disabled", cycle.cycle_id)

        if last_cycle_at is None:
            return AutomationDecision(True, "automation cycle allowed", cycle.cycle_id)

        elapsed = cycle.requested_at - last_cycle_at
        if elapsed < timedelta(seconds=float(policy.minimum_interval_seconds)):
            return AutomationDecision(False, "minimum interval not elapsed", cycle.cycle_id)

        return AutomationDecision(True, "automation cycle allowed", cycle.cycle_id)
