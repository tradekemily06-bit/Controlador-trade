from datetime import datetime, timezone

import pytest

from core.models import AnalysisResult, Signal
from core.mt5_market_analysis_bridge import (
    analyze_mt5_candidates_from_market_data,
    build_mt5_snapshot_analyzer,
)
from core.p122_broker_market_data import BrokerMarketDataBoundary
from data.models import Candle
from execution.mt5_asset_selector import MT5AssetCandidate


class FakeProvider:
    def __init__(self) -> None:
        self.requests = []

    def fetch_market_data(self, request):
        self.requests.append(request)
        return (
            Candle(
                timestamp=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
                open=100,
                high=105,
                low=99,
                close=104,
                volume=10,
            ),
        )


def test_bridge_fetches_validated_snapshot_and_fills_metadata() -> None:
    provider = FakeProvider()
    boundary = BrokerMarketDataBoundary(provider, "IC_MARKETS_MT5_DEMO")

    analyzer = build_mt5_snapshot_analyzer(
        boundary,
        timeframe="5m",
        limit=50,
        evaluator=lambda snapshot: AnalysisResult(
            signal=Signal.AGUARDAR,
            score=50,
            reason=f"{len(snapshot.candles)} candles",
            confirmed=False,
        ),
    )

    result = analyzer("BTCUSD")

    assert result.signal is Signal.AGUARDAR
    assert result.symbol == "BTCUSD"
    assert result.timeframe == "5m"
    assert provider.requests[0].symbol == "BTCUSD"
    assert provider.requests[0].limit == 50


def test_bridge_preserves_evaluator_metadata() -> None:
    provider = FakeProvider()
    boundary = BrokerMarketDataBoundary(provider, "IC_MARKETS_MT5_DEMO")

    result = build_mt5_snapshot_analyzer(
        boundary,
        timeframe="5m",
        limit=20,
        evaluator=lambda snapshot: AnalysisResult(
            signal=Signal.COMPRA,
            score=88,
            reason="confirmed",
            confirmed=True,
            symbol="CUSTOM",
            timeframe="1m",
        ),
    )("BTCUSD")

    assert result.symbol == "CUSTOM"
    assert result.timeframe == "1m"
    assert result.score == 88


def test_multi_asset_bridge_uses_ranked_candidates_and_keeps_read_only() -> None:
    provider = FakeProvider()
    boundary = BrokerMarketDataBoundary(provider, "IC_MARKETS_MT5_DEMO")
    candidates = (
        MT5AssetCandidate("BTCUSD", "crypto", True, 1),
        MT5AssetCandidate("EURUSD", "other", False, 2),
    )

    results = analyze_mt5_candidates_from_market_data(
        candidates,
        boundary,
        timeframe="5m",
        limit=30,
        evaluator=lambda snapshot: AnalysisResult(
            signal=Signal.COMPRA if snapshot.symbol == "BTCUSD" else Signal.AGUARDAR,
            score=90 if snapshot.symbol == "BTCUSD" else 50,
            reason="test",
            confirmed=True,
        ),
    )

    assert [item.result.signal for item in results] == [Signal.COMPRA, Signal.AGUARDAR]
    assert [request.symbol for request in provider.requests] == ["BTCUSD", "EURUSD"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeframe": "", "limit": 10},
        {"timeframe": "5m", "limit": 0},
    ],
)
def test_bridge_rejects_invalid_configuration(kwargs) -> None:
    boundary = BrokerMarketDataBoundary(FakeProvider(), "IC_MARKETS_MT5_DEMO")
    with pytest.raises(ValueError):
        build_mt5_snapshot_analyzer(boundary, evaluator=lambda snapshot: None, **kwargs)
