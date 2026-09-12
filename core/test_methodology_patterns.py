from datetime import datetime, timezone

from core.methodology_features import extract_candle_features
from core.methodology_patterns import observe_patterns
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


def test_careca_is_observed_only_from_zero_wicks():
    features = extract_candle_features(candle(100, 110, 100, 110))

    result = observe_patterns(features)

    assert result.latest_is_careca is True
    assert result.two_same_direction_without_wicks is False
    assert result.previous_wick_symmetry is None


def test_two_same_direction_carecas_are_observed_without_classifying_trade():
    previous = extract_candle_features(candle(100, 110, 100, 110))
    latest = extract_candle_features(candle(110, 120, 110, 120))

    result = observe_patterns(latest, previous)

    assert result.latest_is_careca is True
    assert result.two_same_direction_without_wicks is True
    assert result.latest_wick_symmetry == 1.0
    assert result.previous_wick_symmetry == 1.0


def test_opposite_direction_carecas_do_not_match_same_direction_sequence():
    previous = extract_candle_features(candle(110, 110, 100, 100))
    latest = extract_candle_features(candle(100, 110, 100, 110))

    result = observe_patterns(latest, previous)

    assert result.latest_is_careca is True
    assert result.two_same_direction_without_wicks is False


def test_wick_symmetry_is_exposed_without_a_threshold():
    previous = extract_candle_features(candle(100, 112, 98, 108))
    latest = extract_candle_features(candle(108, 116, 104, 114))

    result = observe_patterns(latest, previous)

    assert result.latest_wick_symmetry == 0.5
    assert result.previous_wick_symmetry == 0.5
