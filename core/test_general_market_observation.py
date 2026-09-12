from datetime import datetime, timedelta

import pytest

from data.models import Candle
from .general_market_observation import observe_general_market_context


def candle(open_: float, high: float, low: float, close: float, volume: float = 0.0, offset: int = 0) -> Candle:
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_observes_broad_sequence_without_named_strategy_rules():
    candles = [
        candle(100, 105, 99, 104, 10, 0),
        candle(104, 108, 103, 107, 15, 1),
        candle(107, 112, 106, 111, 20, 2),
    ]

    observation = observe_general_market_context(candles)

    assert observation is not None
    assert observation.candle_count == 3
    assert observation.directions == ("ALTA", "ALTA", "ALTA")
    assert observation.bullish_count == 3
    assert observation.bearish_count == 0
    assert observation.same_direction_streak == 3
    assert observation.range_change == "UP"
    assert observation.volume_change == "UP"
    assert observation.high_progression == "HIGHER"
    assert observation.low_progression == "HIGHER"
    assert observation.close_progression == "HIGHER"
    assert "LATEST_DIRECTION:ALTA" in observation.observations
    assert "DIRECTION_STREAK:3" in observation.observations


def test_observes_careca_as_raw_context_without_turning_it_into_a_signal():
    observation = observe_general_market_context([
        candle(100, 110, 100, 110, 5),
    ])

    assert observation is not None
    assert observation.observations.count("LATEST_HAS_NO_WICKS:true") == 1
    assert observation.observations[0] == "LATEST_DIRECTION:ALTA"


def test_single_candle_keeps_comparisons_undefined():
    observation = observe_general_market_context([
        candle(100, 110, 98, 105, 7),
    ])

    assert observation is not None
    assert observation.range_change == "UNDEFINED"
    assert observation.body_change == "UNDEFINED"
    assert observation.volume_change == "UNDEFINED"
    assert observation.high_progression == "UNDEFINED"
    assert observation.low_progression == "UNDEFINED"
    assert observation.close_progression == "UNDEFINED"


def test_empty_sequence_returns_none():
    assert observe_general_market_context([]) is None


def test_invalid_candle_fails_closed():
    invalid = candle(100, 90, 95, 96)
    with pytest.raises(ValueError, match="all candles must be valid"):
        observe_general_market_context([invalid])
