from datetime import datetime

from data.models import Candle
from core.general_market_observation import observe_general_market_context
from core.market_context_reasoning import reason_market_context


def test_discovery_flows_into_neutral_context_evidence():
    candles = [
        Candle(datetime(2026, 1, 1, 0, 0), 100, 105, 99, 104, 10),
        Candle(datetime(2026, 1, 1, 0, 1), 104, 108, 103, 107, 15),
    ]

    observation = observe_general_market_context(candles)
    context = reason_market_context(observation)

    assert context is not None
    assert context.discovered_relationships
    assert all("SIGNAL" not in item for item in context.discovered_relationships)
    assert all("SCORE" not in item for item in context.discovered_relationships)
    assert all("RISK" not in item for item in context.discovered_relationships)
