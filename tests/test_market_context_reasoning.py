from datetime import datetime, timedelta

from data.models import Candle
from core.general_market_observation import observe_general_market_context
from core.market_context_reasoning import reason_market_context


def candle(open_: float, high: float, low: float, close: float, volume: float, offset: int) -> Candle:
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_reasoning_combines_observations_without_trade_signal():
    observation = observe_general_market_context([
        candle(100, 105, 99, 104, 10, 0),
        candle(104, 108, 103, 107, 15, 1),
        candle(107, 112, 106, 111, 20, 2),
    ])

    context = reason_market_context(observation)

    assert context is not None
    assert context.directional_balance == "BULLISH_CONTEXT"
    assert context.structure_context == "RISING_BOUNDS"
    assert context.participation_context == "VOLUME_EXPANDING"
    assert context.expansion_context == "RANGE_EXPANDING"
    assert "DIRECTION_STREAK_PRESENT" in context.pattern_context
    assert "RANGE_AND_VOLUME_EXPANSION" in context.pattern_context
    assert "RANGE_CHANGE=UP" in context.discovered_relationships
    assert any(item.startswith("COMBINATION[") for item in context.discovered_relationships)
    assert not hasattr(context, "signal")
    assert not hasattr(context, "score")


def test_reasoning_preserves_mixed_context():
    observation = observe_general_market_context([
        candle(100, 105, 99, 104, 10, 0),
        candle(104, 109, 98, 101, 20, 1),
    ])

    context = reason_market_context(observation)

    assert context is not None
    assert context.directional_balance == "MIXED_CONTEXT"
    assert context.structure_context == "MIXED_BOUNDS"


def test_none_observation_returns_none():
    assert reason_market_context(None) is None
