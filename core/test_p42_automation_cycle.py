from datetime import datetime, timezone

from core.p41_controlled_automation import AutomationDecision
from core.p42_automation_cycle import AutomationCycleOrchestrator


def test_authorized_decision_creates_demo_cycle_request():
    result = AutomationCycleOrchestrator().request_cycle(
        AutomationDecision(True, "ok", "cycle-1"),
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.authorized is True
    assert result.request is not None
    assert result.request.cycle_id == "cycle-1"
    assert result.request.mode == "DEMO"


def test_blocked_decision_does_not_create_request():
    result = AutomationCycleOrchestrator().request_cycle(
        AutomationDecision(False, "blocked", "cycle-2"),
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.authorized is False
    assert result.request is None


def test_invalid_timestamp_fails_closed():
    result = AutomationCycleOrchestrator().request_cycle(
        AutomationDecision(True, "ok", "cycle-3"),
        requested_at=datetime(2026, 1, 1),
    )
    assert result.authorized is False
    assert result.request is None


def test_result_is_immutable():
    result = AutomationCycleOrchestrator().request_cycle(
        AutomationDecision(True, "ok", "cycle-4"),
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    try:
        result.requested_at = None
    except AttributeError:
        pass
