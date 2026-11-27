from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from core.unified_intelligence import UnifiedIntelligence
from data.models import Candle
from data.timeframes import get_timeframe_interval
from integration.standalone_market_analysis import StandaloneMarketAnalysisService
from security.tenant_context import TenantContext


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
    def test_live_candle_is_used_by_the_analysis_pipeline(self):
        candles = candle_series()
        provider = FakeMarketDataProvider(candles)
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="LIVE_OVERLAY_TEST",
            intelligence=UnifiedIntelligence(),
        )
        base = candles[-1]
        live = Candle(
            timestamp=base.timestamp,
            open=base.open,
            high=base.high + 0.001,
            low=base.low,
            close=base.close + 0.0005,
            volume=base.volume + 10,
        )
        result = service.analyze(
            symbol="EURUSD", timeframe="5m", limit=8, live_candle=live
        )
        self.assertEqual(result["market_data"]["last_candle_at"], live.timestamp.isoformat())
        self.assertEqual(result["market_data"]["ohlcv"][-1]["close"], live.close)
        self.assertEqual(result["market_data"]["ohlcv"][-1]["volume"], live.volume)
        self.assertFalse(result["execution_allowed"])

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
        expected_visual = {
            "COMPRA": {"color": "GREEN", "arrow": "UP"},
            "VENDA": {"color": "RED", "arrow": "DOWN"},
            "AGUARDAR": {"color": "YELLOW", "arrow": "NONE"},
        }[card["direction"]]
        self.assertEqual(card["visual"]["color"], expected_visual["color"])
        self.assertEqual(card["visual"]["arrow"], expected_visual["arrow"])
        self.assertEqual(card["visual"]["score_color"], expected_visual["color"])
        self.assertEqual(card["visual"]["profit_probability_color"], "NEUTRAL")
        self.assertEqual(card["timeframe"], "5m")
        self.assertEqual(card["score_type"], "EVIDENCE_STRENGTH")
        self.assertIsNone(card["probability_of_profit"])
        self.assertEqual(card["profit_estimate"]["status"], "NOT_AVAILABLE")
        self.assertIsNone(card["profit_estimate"]["value"])
        self.assertEqual(card["risk_estimate"]["status"], "NOT_AVAILABLE")
        self.assertIsNone(card["risk_estimate"]["value"])
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

    def test_analysis_is_saved_to_decision_memory_with_stable_cycle_identity(self):
        provider = FakeMarketDataProvider(candle_series())
        saved = {}

        def save_once(record):
            if record.decision_id in saved:
                return False
            saved[record.decision_id] = record
            return True

        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="MEMORY_TEST_FEED",
            intelligence=UnifiedIntelligence(),
            decision_sink=save_once,
        )

        first = service.analyze(symbol="EURUSD", timeframe="5m", limit=8)
        second = service.analyze(symbol="EURUSD", timeframe="5m", limit=8)

        self.assertEqual(len(saved), 1)
        record = next(iter(saved.values()))
        self.assertEqual(record.symbol, "EURUSD")
        self.assertEqual(record.timeframe, "5m")
        self.assertEqual(record.signal, first["signal"])
        self.assertEqual(record.signal, second["signal"])
        self.assertFalse(record.execution_allowed)
        self.assertEqual(first["decision_memory"]["status"], "SAVED")
        self.assertEqual(second["decision_memory"]["status"], "ALREADY_RECORDED")
        self.assertEqual(first["decision_memory"]["decision_id"], record.decision_id)


    def test_decision_memory_identity_isolated_by_provider_account_source(self):
        provider = FakeMarketDataProvider(candle_series())
        intelligence = UnifiedIntelligence()
        account_a = StandaloneMarketAnalysisService(
            provider=provider, source="broker:account-a", intelligence=intelligence
        )
        account_b = StandaloneMarketAnalysisService(
            provider=provider, source="broker:account-b", intelligence=intelligence
        )
        candle_at = "2026-11-27T12:00:00+00:00"
        id_a = account_a._decision_record_id("EURUSD", "5m", candle_at)
        id_b = account_b._decision_record_id("EURUSD", "5m", candle_at)
        self.assertNotEqual(id_a, id_b)
        self.assertEqual(
            id_a, account_a._decision_record_id("EURUSD", "5m", candle_at)
        )

    def test_decision_memory_failure_is_reported_without_faking_persistence(self):
        def fail_save(_record):
            raise OSError("storage unavailable")

        service = StandaloneMarketAnalysisService(
            provider=FakeMarketDataProvider(candle_series()),
            source="MEMORY_FAILURE_TEST_FEED",
            intelligence=UnifiedIntelligence(),
            decision_sink=fail_save,
        )
        result = service.analyze(symbol="EURUSD", timeframe="5m", limit=8)
        self.assertEqual(result["decision_memory"]["status"], "PERSISTENCE_ERROR")
        self.assertEqual(result["decision_memory"]["error_class"], "OSError")

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

    def test_platform_timeframe_alias_and_custom_interval_are_supported(self):
        provider = FakeMarketDataProvider(candle_series(timeframe="2m"))
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="CUSTOM_INTERVAL_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )
        result = service.analyze(symbol="EURUSD", timeframe="M2", limit=8)
        self.assertEqual(result["timeframe"], "2m")
        self.assertEqual(provider.requests[0].timeframe, "2m")
        self.assertFalse(result["execution_authorized"])

    def test_daily_weekly_fail_closed_without_provider_session_calendar(self):
        for timeframe in ("1d", "1w"):
            with self.subTest(timeframe=timeframe):
                provider = FakeMarketDataProvider(
                    candle_series(timeframe=timeframe, age_intervals=1)
                )
                evidence_calls = []
                outcome_calls = []
                service = StandaloneMarketAnalysisService(
                    provider=provider,
                    source="SESSION_CALENDAR_TEST_FEED",
                    intelligence=UnifiedIntelligence(),
                    market_data_provenance="REAL_MARKET_DATA",
                    signal_source_id="session-calendar-test",
                    signal_evidence_sink=lambda *args, **kwargs: evidence_calls.append(kwargs),
                    signal_outcome_sink=lambda *args, **kwargs: outcome_calls.append(kwargs),
                )

                result = service.analyze(
                    symbol="EURUSD",
                    timeframe=timeframe,
                    limit=8,
                    decision_context=TenantContext("tenant-a", "subject-a"),
                )

                self.assertEqual(result["signal"], "AGUARDAR")
                self.assertEqual(result["status"], "REASSESS_REQUIRED")
                self.assertEqual(
                    result["signal_cycle"]["status"],
                    "SESSION_CALENDAR_UNAVAILABLE",
                )
                self.assertIsNone(result["signal_cycle"]["valid_until"])
                self.assertFalse(result["data_integrity"]["safe_for_analysis"])
                self.assertEqual(
                    result["data_integrity"]["session_calendar_status"],
                    "SESSION_CALENDAR_UNAVAILABLE",
                )
                self.assertEqual(evidence_calls, [])
                self.assertEqual(outcome_calls, [])
                self.assertFalse(result["execution_allowed"])

    def test_unsupported_timeframe_and_unbounded_limit_are_rejected(self):
        service = StandaloneMarketAnalysisService(
            provider=FakeMarketDataProvider(candle_series()),
            source="VALIDATION_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )
        with self.assertRaises(ValueError):
            service.analyze(symbol="EURUSD", timeframe="M0")
        with self.assertRaises(ValueError):
            service.analyze(symbol="EURUSD", timeframe="5m", limit=100000)


    def test_signal_cycle_expires_at_next_timeframe_close(self):
        interval = get_timeframe_interval("5m")
        candles = candle_series(timeframe="5m", age_intervals=2)
        # The latest closed candle's next-cycle close is already due.
        provider = FakeMarketDataProvider(candles)
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="EXPIRED_CYCLE_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )

        result = service.analyze(symbol="EURUSD", timeframe="5m", limit=8)

        self.assertEqual(result["signal"], "AGUARDAR")
        self.assertEqual(result["signal_cycle"]["status"], "EXPIRED_OR_DATA_UNSAFE")
        self.assertFalse(result["execution_allowed"])

    def test_delayed_one_minute_feed_forces_wait(self):
        provider = FakeMarketDataProvider(
            candle_series(timeframe="1m", age_intervals=5)
        )
        service = StandaloneMarketAnalysisService(
            provider=provider,
            source="DELAYED_ONE_MINUTE_TEST_FEED",
            intelligence=UnifiedIntelligence(),
        )

        result = service.analyze(symbol="EURUSD", timeframe="1m", limit=8)

        self.assertTrue(result["data_integrity"]["stale"])
        self.assertEqual(result["signal"], "AGUARDAR")
        self.assertEqual(result["status"], "REASSESS_REQUIRED")
        self.assertFalse(result["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
