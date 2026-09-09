import pytest

from core.p46_automation_lifecycle import (
    AutomationLifecycle,
    AutomationLifecycleBoundary,
    AutomationLifecycleState,
)


def test_happy_path_is_monotonic() -> None:
    boundary = AutomationLifecycleBoundary()
    state = AutomationLifecycle("cycle-46", AutomationLifecycleState.CREATED)
    state = boundary.transition(state, AutomationLifecycleState.ADMITTED)
    state = boundary.transition(state, AutomationLifecycleState.DISPATCHED)
    state = boundary.transition(state, AutomationLifecycleState.COMPLETED)
    assert state.state is AutomationLifecycleState.COMPLETED


def test_blocked_is_terminal() -> None:
    boundary = AutomationLifecycleBoundary()
    state = boundary.transition(
        AutomationLifecycle("cycle-46", AutomationLifecycleState.CREATED),
        AutomationLifecycleState.BLOCKED,
    )
    assert state.state is AutomationLifecycleState.BLOCKED
    with pytest.raises(ValueError):
        boundary.transition(state, AutomationLifecycleState.ADMITTED)


def test_terminal_state_cannot_be_reused() -> None:
    boundary = AutomationLifecycleBoundary()
    for terminal in (AutomationLifecycleState.COMPLETED, AutomationLifecycleState.BLOCKED):
        with pytest.raises(ValueError):
            boundary.transition(AutomationLifecycle("c", terminal), AutomationLifecycleState.CREATED)


def test_invalid_transition_fails_closed() -> None:
    with pytest.raises(ValueError):
        AutomationLifecycleBoundary().transition(
            AutomationLifecycle("c", AutomationLifecycleState.CREATED),
            AutomationLifecycleState.DISPATCHED,
        )


def test_empty_cycle_id_fails_closed() -> None:
    with pytest.raises(ValueError):
        AutomationLifecycleBoundary().transition(
            AutomationLifecycle("", AutomationLifecycleState.CREATED),
            AutomationLifecycleState.ADMITTED,
        )


def test_snapshots_are_immutable() -> None:
    state = AutomationLifecycle("c", AutomationLifecycleState.CREATED)
    with pytest.raises(AttributeError):
        state.state = AutomationLifecycleState.BLOCKED  # type: ignore[misc]
