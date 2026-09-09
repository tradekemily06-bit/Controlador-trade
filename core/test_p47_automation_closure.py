from datetime import datetime, timezone

import pytest

from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState
from core.p47_automation_closure import AutomationClosureBoundary


def test_completed_cycle_can_close() -> None:
    lifecycle = AutomationLifecycle("cycle-47", AutomationLifecycleState.COMPLETED)
    closed_at = datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc)
    result = AutomationClosureBoundary().close(lifecycle, closed_at=closed_at)
    assert result.cycle_id == "cycle-47"
    assert result.terminal_state is AutomationLifecycleState.COMPLETED
    assert result.closed_at == closed_at


def test_blocked_cycle_can_close() -> None:
    lifecycle = AutomationLifecycle("cycle-47", AutomationLifecycleState.BLOCKED)
    result = AutomationClosureBoundary().close(
        lifecycle, closed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc)
    )
    assert result.terminal_state is AutomationLifecycleState.BLOCKED


def test_non_terminal_cycle_cannot_close() -> None:
    lifecycle = AutomationLifecycle("cycle-47", AutomationLifecycleState.DISPATCHED)
    with pytest.raises(ValueError):
        AutomationClosureBoundary().close(
            lifecycle, closed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc)
        )


def test_naive_timestamp_fails_closed() -> None:
    lifecycle = AutomationLifecycle("cycle-47", AutomationLifecycleState.COMPLETED)
    with pytest.raises(ValueError):
        AutomationClosureBoundary().close(lifecycle, closed_at=datetime(2026, 9, 9, 12, 1))


def test_closure_is_immutable_and_has_no_financial_result() -> None:
    result = AutomationClosureBoundary().close(
        AutomationLifecycle("cycle-47", AutomationLifecycleState.COMPLETED),
        closed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(AttributeError):
        result.cycle_id = "changed"  # type: ignore[misc]
    assert not hasattr(result, "profit")
    assert not hasattr(result, "loss")
    assert not hasattr(result, "win")
