from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from core.unified_intelligence import UnifiedIntelligence
from data.models import Candle
from data.timeframes import get_timeframe_interval
from integration.standalone_market_analysis import StandaloneMarketAnalysisService


class FakeMarketDataProvider:
    def __init__(self, candles):
        self.candles = tuple(candles)
        self.requests = []

    def fetch(self, request):
        self.requests.append(request)
        return self.candles[-request.limit:]


def candle_series(timeframe="5m", count=8, age_intervals=1):
    interval = get_timeframe_interval(timeframe)
    now = datetime.now().astimezone()
    last_open = now - interval * age_intervals
    result = []
    for index in range(count):
        timestamp = last_open - interval * (count - index - 1)
        base = 1.0 + index * 0.001
        result.append(Candle(
            timestamp=timestamp,
            open=base,
            high=base + 0.002,
            low=base - 0.001,
            close=base + 0.001,
            volume=100 + index,
        ))
    return result


class StandaloneMarketAnalysisTests(unittest.TestCase):
    def test_provider_neutral_analysis_never_authorizes_execution(self):
        provider = FakeMarketDataProvider(candle_series())
        intelligence = UnifiedIntelligence()
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="FAKE_TEST_FEED",
            intelligence=intelligence,
        )

        result = service.analyze(
            symbol="EURUSD",
            timeframe="5m",
            limit=8,
            confirmed=True,
            filters_ok=True,
        )

        self.assertEqual(result["decision"], "ANALYSIS_ONLY")
        card = result["signal_card"]
        self.assertEqual(card["symbol"], "EURUSD")
        self.assertEqual(card["direction"], result["signal"])
        self.assertEqual(card["timeframe"], "5m")
        self.assertEqual(card["score_type"], "EVIDENCE_STRENGTH")
        self.assertIsNone(card["probability_of_profit"])
        self.assertEqual(card["profit_probability"]["status"], "NOT_CALIBRATED")
        self.assertIsNone(card["profit_probability"]["value"])
        self.assertTrue(card["profit_probability"]["calibration_required"])
        self.assertTrue(card["manual_entry_only"])
        self.assertFalse(card["execution_authorized"])
        self.assertFalse(card["order_submitted"])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["order_submitted"])
        self.assertEqual(result["market_data"]["source"], "FAKE_TEST_FEED")
        self.assertIn(result["signal"], {"COMPRA", "VENDA", "AGUARDAR"})

    def test_stale_market_data_forces_wait(self):
        provider = FakeMarketDataProvider(candle_series(age_intervals=20))
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="STALE_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )
        result = service.analyze(symbol="EURUSD", timeframe="5m", limit=8)
        self.assertEqual(result["signal"], "AGUARDAR")
        self.assertEqual(result["status"], "REASSESS_REQUIRED")
        self.assertFalse(result["execution_allowed"])

    def test_ten_minute_timeframe_is_supported(self):
        self.assertEqual(get_timeframe_interval("10m"), timedelta(minutes=10))
        provider = FakeMarketDataProvider(candle_series(timeframe="10m"))
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="TEN_MINUTE_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )
        result = service.analyze(symbol="EURUSD", timeframe="10m", limit=8)
        self.assertEqual(result["timeframe"], "10m")
        self.assertFalse(result["execution_authorized"])

    def test_unsupported_timeframe_and_unbounded_limit_are_rejected(self):
        service = StandaloneMarketAnalysisService(
            provider=FakeMarketDataProvider(candle_series()),
            source="VALIDATION_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )
        with self.assertRaises(ValueError):
            service.analyze(symbol="EURUSD", timeframe="2m")
        with self.assertRaises(ValueError):
            service.analyze(symbol="EURUSD", timeframe="5m", limit=100000)


if __name__ == "__main__":
    unittest.main()
