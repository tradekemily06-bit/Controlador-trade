from dataclasses import dataclass
from datetime import datetime, timedelta

from data.models import Candle
from core.general_market_observation import GeneralMarketObservation, observe_general_market_context
from core.market_discovery import discover_market_relationships


def candle(open_: float, high: float, low: float, close: float, volume: float, offset: int) -> Candle:
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_discovery_exposes_relationships_without_decision_fields():
    observation = observe_general_market_context([
        candle(100, 105, 99, 104, 10, 0),
        candle(104, 108, 103, 107, 15, 1),
        candle(107, 112, 106, 111, 20, 2),
    ])

    relationships = discover_market_relationships(observation)

    assert "RANGE_CHANGE=UP" in relationships
    assert "VOLUME_CHANGE=UP" in relationships
    assert "RANGE_DIRECTION=UP" in relationships
    assert "VOLUME_DIRECTION=UP" in relationships
    assert any(item.startswith("COMBINATION[") for item in relationships)
    assert not any("SIGNAL" in item or "SCORE" in item for item in relationships)


def test_discovery_picks_up_new_observation_fields_without_pattern_registry():
    @dataclass(frozen=True)
    class ExtendedObservation(GeneralMarketObservation):
        future_context: str = "NOVEL_CONTEXT"

    base = observe_general_market_context([
        candle(100, 105, 99, 104, 10, 0),
        candle(104, 108, 103, 107, 15, 1),
    ])
    extended = ExtendedObservation(**base.__dict__)

    relationships = discover_market_relationships(extended)

    assert "FUTURE_CONTEXT=NOVEL_CONTEXT" in relationships


def test_none_observation_is_empty():
    assert discover_market_relationships(None) == ()
