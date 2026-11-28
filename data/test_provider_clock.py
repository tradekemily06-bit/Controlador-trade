from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from data.provider_clock import expected_last_closed_candle


def test_m1_uses_mt5_broker_clock_and_normalizes_result_to_utc():
    broker_now = datetime(2026, 11, 28, 13, 5, 5, tzinfo=timezone(timedelta(hours=3)))
    assert expected_last_closed_candle("M1", provider_now=broker_now) == datetime(2026, 11, 28, 10, 4, tzinfo=timezone.utc)


def test_m5_and_m10_use_their_own_provider_boundaries():
    broker_now = datetime(2026, 11, 28, 13, 5, 5, tzinfo=timezone(timedelta(hours=3)))
    assert expected_last_closed_candle("M5", provider_now=broker_now) == datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc)
    assert expected_last_closed_candle("M10", provider_now=broker_now) == datetime(2026, 11, 28, 9, 50, tzinfo=timezone.utc)


def test_daily_candle_boundary_uses_provider_local_midnight():
    broker_now = datetime(2026, 11, 28, 0, 0, 5, tzinfo=timezone(timedelta(hours=3)))
    assert expected_last_closed_candle("D1", provider_now=broker_now) == datetime(2026, 11, 26, 21, 0, tzinfo=timezone.utc)


def test_weekly_candle_boundary_uses_provider_local_monday():
    broker_now = datetime(2026, 11, 30, 0, 0, 5, tzinfo=ZoneInfo("Europe/Helsinki"))
    expected = datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc)
    assert expected_last_closed_candle("W1", provider_now=broker_now) == expected


def test_provider_timestamp_must_be_timezone_aware():
    with pytest.raises(ValueError):
        expected_last_closed_candle("M1", provider_now=datetime(2026, 11, 28, 13, 5, 5))


def test_close_grace_must_be_non_negative():
    now = datetime(2026, 11, 28, 13, 5, 5, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        expected_last_closed_candle("M1", provider_now=now, close_grace_seconds=-1)
