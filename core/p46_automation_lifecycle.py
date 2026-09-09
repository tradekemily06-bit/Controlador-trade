from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AutomationLifecycleState(str, Enum):
    CREATED = "CREATED"
    ADMITTED = "ADMITTED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


_ALLOWED: dict[AutomationLifecycleState, frozenset[AutomationLifecycleState]] = {
    AutomationLifecycleState.CREATED: frozenset({AutomationLifecycleState.ADMITTED, AutomationLifecycleState.BLOCKED}),
    AutomationLifecycleState.ADMITTED: frozenset({AutomationLifecycleState.DISPATCHED, AutomationLifecycleState.BLOCKED}),
    AutomationLifecycleState.DISPATCHED: frozenset({AutomationLifecycleState.COMPLETED, AutomationLifecycleState.BLOCKED}),
    AutomationLifecycleState.COMPLETED: frozenset(),
    AutomationLifecycleState.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class AutomationLifecycle:
    cycle_id: str
    state: AutomationLifecycleState


class AutomationLifecycleBoundary:
    """Pure state-transition boundary; it never dispatches an operation."""

    def transition(
        self,
        current: AutomationLifecycle,
        target: AutomationLifecycleState,
    ) -> AutomationLifecycle:
        if not isinstance(current, AutomationLifecycle):
            raise ValueError("invalid automation lifecycle")
        if not isinstance(target, AutomationLifecycleState):
            raise ValueError("invalid automation lifecycle target")
        if not isinstance(current.cycle_id, str) or not current.cycle_id.strip():
            raise ValueError("cycle_id is required")
        if target not in _ALLOWED[current.state]:
            raise ValueError(f"invalid automation lifecycle transition: {current.state.value} -> {target.value}")
        return AutomationLifecycle(current.cycle_id, target)
