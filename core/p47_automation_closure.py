from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState


@dataclass(frozen=True)
class AutomationClosure:
    cycle_id: str
    terminal_state: AutomationLifecycleState
    closed_at: datetime


class AutomationClosureBoundary:
    """Closes only terminal cycle state; it never derives financial outcomes."""

    def close(self, lifecycle: AutomationLifecycle, *, closed_at: datetime) -> AutomationClosure:
        if not isinstance(lifecycle, AutomationLifecycle):
            raise ValueError("invalid automation lifecycle")
        if lifecycle.state not in {
            AutomationLifecycleState.COMPLETED,
            AutomationLifecycleState.BLOCKED,
        }:
            raise ValueError("only terminal automation states can be closed")
        if not isinstance(closed_at, datetime) or closed_at.tzinfo is None or closed_at.utcoffset() is None:
            raise ValueError("closed_at must be timezone-aware")
        if not isinstance(lifecycle.cycle_id, str) or not lifecycle.cycle_id.strip():
            raise ValueError("cycle_id is required")
        return AutomationClosure(lifecycle.cycle_id, lifecycle.state, closed_at)
