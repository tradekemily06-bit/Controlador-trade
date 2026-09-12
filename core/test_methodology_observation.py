from datetime import datetime, timezone

from core.methodology_observation import observe_candles
from data.models import Candle


def candle(open_, high, low, close, minute):
    return Candle(
        timestamp=datetime(2026, 9, 12, 12, minute, tzinfo=timezone.utc),
        open=open_, high=high, low=low, close=close, volume=100,
    )


def test_observation_exposes_latest_and_previous_candle_facts():
    observation = observe_candles([
        candle(100, 103, 99, 102, 0),
        candle(102, 108, 101, 107, 5),
    ])

    assert observation is not None
    assert observation.latest.direction == "ALTA"
    assert observation.latest.body_size == 5
    assert observation.latest.upper_wick == 1
    assert observation.latest.lower_wick == 1
    assert observation.previous is not None
    assert observation.same_direction is True
    assert observation.patterns.latest_is_careca is False
    assert observation.patterns.two_same_direction_without_wicks is False
    assert observation.patterns.previous_wick_symmetry == 1.0


def test_observation_is_empty_for_no_candles():
    assert observe_candles([]) is None
