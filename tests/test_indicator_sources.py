from datetime import datetime, timedelta, timezone

import pytest

from core.indicator_sources import (
    ExternalIndicatorReading,
    IndicatorSourceKind,
    is_fresh_indicator_reading,
)


def reading(**overrides):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    values = dict(
        provider="test-provider",
        source_kind=IndicatorSourceKind.EXTERNAL_SITE,
        symbol="EURUSD",
        timeframe="M5",
        observed_at=now,
        candle_timestamp=now - timedelta(minutes=5),
        values={"rsi_14": 53.2, "macd": 0.001},
    )
    values.update(overrides)
    return ExternalIndicatorReading(**values)


def test_accepts_normalized_external_indicator_reading():
    result = reading()
    assert result.source_kind is IndicatorSourceKind.EXTERNAL_SITE
    assert result.values["rsi_14"] == 53.2


def test_rejects_non_finite_indicator_values():
    with pytest.raises(ValueError, match="finite numeric"):
        reading(values={"rsi_14": float("nan")})


def test_rejects_future_candle_timestamp():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="after observation"):
        reading(candle_timestamp=now + timedelta(seconds=1))


def test_freshness_rejects_old_and_future_observations():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    assert is_fresh_indicator_reading(reading(), now=now)
    assert not is_fresh_indicator_reading(
        reading(observed_at=now - timedelta(minutes=10)),
        now=now,
    )
    assert not is_fresh_indicator_reading(
        reading(observed_at=now + timedelta(seconds=1)),
        now=now,
    )


def test_requires_timezone_aware_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        reading(observed_at=datetime(2026, 10, 10, 12))
