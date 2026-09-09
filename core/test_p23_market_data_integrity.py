from datetime import datetime, timedelta, timezone

import pytest

from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrity
from data.models import Candle


def candle_at(base: datetime, minutes: int) -> Candle:
    return Candle(base + timedelta(minutes=minutes), 100, 101, 99, 100, 1)


def test_healthy_data():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = tuple(candle_at(base, i) for i in range(3))
    report = MarketDataIntegrity().assess(data, now=base + timedelta(minutes=3), expected_interval_seconds=60)
    assert report.health is MarketDataHealth.HEALTHY


def test_stale_data():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = (candle_at(base, 0),)
    report = MarketDataIntegrity(max_age_seconds=30).assess(data, now=base + timedelta(minutes=1))
    assert report.health is MarketDataHealth.STALE


def test_gap_data():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = tuple(candle_at(base, i) for i in (0, 2))
    report = MarketDataIntegrity().assess(data, now=base + timedelta(minutes=2), expected_interval_seconds=60)
    assert report.health is MarketDataHealth.GAP
    assert report.gap_count == 1


def test_invalid_order_is_rejected():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = (candle_at(base, 1), candle_at(base, 0))
    report = MarketDataIntegrity().assess(data, now=base + timedelta(minutes=2), expected_interval_seconds=60)
    assert report.health is MarketDataHealth.INVALID


def test_duplicate_timestamp_is_rejected():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = (candle_at(base, 0), candle_at(base, 0))
    report = MarketDataIntegrity().assess(data, now=base + timedelta(minutes=1), expected_interval_seconds=60)
    assert report.health is MarketDataHealth.INVALID


def test_future_timestamp_is_rejected():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = (candle_at(base, 1),)
    report = MarketDataIntegrity().assess(data, now=base)
    assert report.health is MarketDataHealth.INVALID


def test_timezone_mismatch_is_rejected():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = (candle_at(base, 0),)
    with pytest.raises(ValueError):
        # A mismatched timezone regime is represented by a naive now.
        MarketDataIntegrity().assess(data, now=base.replace(tzinfo=None))


def test_invalid_interval_configuration():
    with pytest.raises(ValueError):
        MarketDataIntegrity().assess((), now=datetime.now(timezone.utc), expected_interval_seconds=0)
