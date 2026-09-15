from datetime import datetime, timedelta, timezone

from core.decision_freshness import DecisionFreshnessPolicy


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_fresh_decision_is_allowed():
    policy = DecisionFreshnessPolicy(max_age_seconds=30)
    assert policy.validate(NOW - timedelta(seconds=29), now=NOW) is None


def test_expired_decision_is_blocked():
    policy = DecisionFreshnessPolicy(max_age_seconds=30)
    reason = policy.validate(NOW - timedelta(seconds=31), now=NOW)
    assert reason is not None
    assert "expirada" in reason


def test_future_decision_is_blocked_beyond_allowed_clock_skew():
    policy = DecisionFreshnessPolicy(max_age_seconds=30, max_future_skew_seconds=2)
    reason = policy.validate(NOW + timedelta(seconds=3), now=NOW)
    assert reason is not None
    assert "futuro" in reason


def test_naive_timestamp_is_fail_closed():
    policy = DecisionFreshnessPolicy(max_age_seconds=30)
    reason = policy.validate(NOW.replace(tzinfo=None), now=NOW)
    assert reason is not None
    assert "timezone" in reason
