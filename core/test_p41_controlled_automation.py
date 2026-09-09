from datetime import datetime, timedelta, timezone

import pytest

from core.p41_controlled_automation import (
    AutomationCycle,
    AutomationPolicy,
    ControlledAutomationGate,
)


UTC = timezone.utc


def cycle(at, cycle_id="c1"):
    return AutomationCycle(cycle_id=cycle_id, requested_at=at)


def test_disabled_automation_blocks():
    policy = AutomationPolicy(enabled=False, minimum_interval_seconds=60)
    result = ControlledAutomationGate().evaluate(policy, cycle(datetime(2026, 1, 1, tzinfo=UTC)))
    assert result.allowed is False
    assert result.reason == "automation disabled"


def test_first_enabled_cycle_is_allowed():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=60)
    result = ControlledAutomationGate().evaluate(policy, cycle(datetime(2026, 1, 1, tzinfo=UTC)))
    assert result.allowed is True


def test_minimum_interval_blocks_early_cycle():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=60)
    last = datetime(2026, 1, 1, tzinfo=UTC)
    current = last + timedelta(seconds=59)
    result = ControlledAutomationGate().evaluate(policy, cycle(current), last_cycle_at=last)
    assert result.allowed is False
    assert result.reason == "minimum interval not elapsed"


def test_minimum_interval_allows_boundary():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=60)
    last = datetime(2026, 1, 1, tzinfo=UTC)
    current = last + timedelta(seconds=60)
    result = ControlledAutomationGate().evaluate(policy, cycle(current), last_cycle_at=last)
    assert result.allowed is True


def test_time_regression_blocks():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=0)
    last = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    current = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    result = ControlledAutomationGate().evaluate(policy, cycle(current), last_cycle_at=last)
    assert result.allowed is False
    assert result.reason == "cycle timestamp precedes last cycle"


def test_invalid_policy_and_cycle_fail_closed():
    with pytest.raises(ValueError):
        AutomationPolicy(enabled=True, minimum_interval_seconds=float("nan"))
    with pytest.raises(ValueError):
        AutomationCycle(cycle_id="", requested_at=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        AutomationCycle(cycle_id="c1", requested_at=datetime(2026, 1, 1))


def test_invalid_last_cycle_fails_closed():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=0)
    current = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        ControlledAutomationGate().evaluate(policy, cycle(current), last_cycle_at=datetime(2026, 1, 1))


def test_decision_is_immutable():
    policy = AutomationPolicy(enabled=True, minimum_interval_seconds=0)
    result = ControlledAutomationGate().evaluate(
        policy, cycle(datetime(2026, 1, 1, tzinfo=UTC), "immutable")
    )
    with pytest.raises((AttributeError, TypeError)):
        result.allowed = False
