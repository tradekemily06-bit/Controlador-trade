from datetime import datetime, timezone

import pytest

from core.methodology_features import extract_candle_features, same_direction
from data.models import Candle


def candle(open_, high, low, close):
    return Candle(
        timestamp=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_extracts_body_and_wicks_without_inventing_signal():
    features = extract_candle_features(candle(100, 110, 98, 108))

    assert features.direction == "ALTA"
    assert features.range_size == 12
    assert features.body_size == 8
    assert features.upper_wick == 2
    assert features.lower_wick == 2
    assert features.body_ratio == pytest.approx(8 / 12)
    assert features.upper_wick_ratio == pytest.approx(2 / 12)
    assert features.lower_wick_ratio == pytest.approx(2 / 12)
    assert features.close_position == pytest.approx(10 / 12)
    assert features.has_no_wicks is False
    assert features.wick_symmetry == pytest.approx(1.0)


def test_identifies_a_candle_without_wicks():
    features = extract_candle_features(candle(100, 110, 100, 110))

    assert features.direction == "ALTA"
    assert features.has_no_upper_wick is True
    assert features.has_no_lower_wick is True
    assert features.has_no_wicks is True
    assert features.body_ratio == pytest.approx(1.0)


def test_same_direction_only_accepts_non_neutral_candles():
    up = extract_candle_features(candle(100, 105, 99, 104))
    up2 = extract_candle_features(candle(104, 108, 103, 107))
    down = extract_candle_features(candle(107, 108, 102, 103))
    neutral = extract_candle_features(candle(105, 108, 102, 105))

    assert same_direction(up, up2) is True
    assert same_direction(up, down) is False
    assert same_direction(up, neutral) is False


def test_invalid_candle_fails_closed():
    invalid = candle(100, 99, 100, 99)

    with pytest.raises(ValueError):
        extract_candle_features(invalid)
