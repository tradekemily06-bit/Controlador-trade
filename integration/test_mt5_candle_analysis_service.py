from datetime import datetime, timezone
from core.models import Signal
from core.p122_broker_market_data import BrokerMarketDataBoundary, BrokerMarketDataRequest
from data.models import Candle
from execution.mt5_asset_selector import MT5AssetCandidate
from integration.mt5_candle_analysis_service import analyze_mt5_candidates_with_default_candle_method

class FakeProvider:
    def fetch_market_data(self, request: BrokerMarketDataRequest):
        return (Candle(datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc), 100, 103, 99, 102, 100), Candle(datetime(2026, 9, 12, 12, 5, tzinfo=timezone.utc), 102, 108, 101, 107, 120))

def test_default_method_wires_ranked_assets_to_candle_evaluator():
    boundary = BrokerMarketDataBoundary(FakeProvider(), "IC_MARKETS_MT5_DEMO")
    candidates = (MT5AssetCandidate("BTCUSD", "crypto", True, 1), MT5AssetCandidate("EURUSD", "other", False, 2))
    results = analyze_mt5_candidates_with_default_candle_method(candidates, boundary, timeframe="5m", limit=20)
    assert len(results) == 2
    assert results[0].result.signal is Signal.COMPRA
    assert results[0].result.symbol == "BTCUSD"
    assert results[0].result.timeframe == "5m"
