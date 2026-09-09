from datetime import datetime, timezone

import pytest

from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState
from core.p47_automation_closure import AutomationClosure
from core.p48_automation_outcome import AutomationOutcomeBoundary


def closure(state=AutomationLifecycleState.COMPLETED):
    return AutomationClosure("cycle-48", state, datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc))


def test_records_explicit_outcome_without_derivation():
    result = AutomationOutcomeBoundary().record(
        closure(), observed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), outcome="WIN", financial_result=12.5
    )
    assert result.cycle_id == "cycle-48"
    assert result.outcome == "WIN"
    assert result.financial_result == 12.5


def test_unknown_has_no_financial_result():
    result = AutomationOutcomeBoundary().record(
        closure(), observed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), outcome="UNKNOWN"
    )
    assert result.financial_result is None


def test_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        AutomationOutcomeBoundary().record(
            closure(), observed_at=datetime(2026, 9, 9, 12, 1), outcome="WIN"
        )


def test_rejects_unknown_with_financial_result():
    with pytest.raises(ValueError):
        AutomationOutcomeBoundary().record(
            closure(), observed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), outcome="UNKNOWN", financial_result=1
        )


def test_blocked_cycle_cannot_receive_financial_outcome():
    with pytest.raises(ValueError):
        AutomationOutcomeBoundary().record(
            closure(AutomationLifecycleState.BLOCKED),
            observed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc),
            outcome="LOSS",
        )


def test_outcome_is_immutable():
    result = AutomationOutcomeBoundary().record(
        closure(), observed_at=datetime(2026, 9, 9, 12, 1, tzinfo=timezone.utc), outcome="DRAW"
    )
    with pytest.raises(Exception):
        result.outcome = "WIN"
