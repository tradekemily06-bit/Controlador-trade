from datetime import datetime, timezone

from integration.market_timeframe_monitor import MarketTimeframeMonitor


class FakeAnalyzer:
    def __init__(self):
        self.results = {}
        self.calls = []

    def analyze(self, *, symbol, timeframe, limit, confirmed, filters_ok):
        self.calls.append((symbol, timeframe, limit, confirmed, filters_ok))
        return self.results[timeframe]


def analysis_result(candle_at, signal="AGUARDAR"):
    return {
        "signal": signal,
        "status": "ANALYZED",
        "market_data": {"last_candle_at": candle_at.isoformat()},
        "execution_authorized": False,
        "order_submitted": False,
    }


def test_monitor_subscribes_to_custom_and_platform_timeframes_persistently(tmp_path):
    analyzer = FakeAnalyzer()
    path = tmp_path / "monitor.sqlite3"
    monitor = MarketTimeframeMonitor(path, analyzer)

    assert monitor.subscribe("eurusd", "M1") == {
        "symbol": "EURUSD", "timeframe": "1m", "enabled": True
    }
    assert monitor.subscribe("EURUSD", "M10")["timeframe"] == "10m"
    assert monitor.subscribe("GBPUSD", "H2")["timeframe"] == "2h"

    restored = MarketTimeframeMonitor(path, analyzer)
    assert {(x["symbol"], x["timeframe"]) for x in restored.subscriptions()} == {
        ("EURUSD", "1m"), ("EURUSD", "10m"), ("GBPUSD", "2h")
    }


def test_expected_last_closed_candle_uses_each_interval_boundary(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer())
    now = datetime(2026, 9, 7, 10, 5, 5, tzinfo=timezone.utc)

    assert monitor.expected_last_closed_candle("M1", now=now) == datetime(
        2026, 9, 7, 10, 4, tzinfo=timezone.utc
    )
    assert monitor.expected_last_closed_candle("M5", now=now) == datetime(
        2026, 9, 7, 10, 0, tzinfo=timezone.utc
    )
    assert monitor.expected_last_closed_candle("M10", now=now) == datetime(
        2026, 9, 7, 9, 50, tzinfo=timezone.utc
    )


def test_monitor_processes_only_the_expected_closed_candle_once(tmp_path):
    analyzer = FakeAnalyzer()
    notifications = []
    monitor = MarketTimeframeMonitor(
        tmp_path / "monitor.sqlite3",
        analyzer,
        on_result=notifications.append,
    )
    monitor.subscribe("EURUSD", "M5")
    now = datetime(2026, 9, 7, 10, 5, 5, tzinfo=timezone.utc)
    analyzer.results["5m"] = analysis_result(
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        signal="COMPRA",
    )

    first = monitor.run_once(now=now)
    second = monitor.run_once(now=now)

    assert len(first) == 1
    assert second == []
    assert len(analyzer.calls) == 1
    assert notifications[0]["result"]["signal"] == "COMPRA"
    assert monitor.subscriptions()[0]["last_signal"] == "COMPRA"


def test_monitor_waits_when_provider_has_not_returned_closed_target_candle(tmp_path):
    analyzer = FakeAnalyzer()
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", analyzer)
    monitor.subscribe("EURUSD", "M5")
    analyzer.results["5m"] = analysis_result(
        datetime(2026, 9, 7, 9, 55, tzinfo=timezone.utc),
        signal="VENDA",
    )

    result = monitor.run_once(
        now=datetime(2026, 9, 7, 10, 5, 5, tzinfo=timezone.utc)
    )

    assert result == []
    assert monitor.subscriptions()[0]["status"] == "WAITING_FOR_CLOSED_CANDLE"
    assert monitor.subscriptions()[0]["last_processed_candle"] is None


def test_monitor_rejects_invalid_symbols_and_timeframes(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer())

    for symbol, timeframe in (("../EURUSD", "5m"), ("EURUSD", "M0")):
        try:
            monitor.subscribe(symbol, timeframe)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid watch subscription was accepted")


def test_monitor_can_disable_a_subscription(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer())
    monitor.subscribe("EURUSD", "M5")

    assert monitor.unsubscribe("EURUSD", "M5")
    assert not monitor.unsubscribe("EURUSD", "M5")
    assert monitor.status()["enabled"] == 0
