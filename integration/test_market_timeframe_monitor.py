from datetime import datetime, timezone

from integration.market_timeframe_monitor import MarketTimeframeMonitor
from security.tenant_context import TenantContext


OWNER = TenantContext(tenant_id="tenant-local", subject_id="owner-local")


class FakeAnalyzer:
    def __init__(self):
        self.results = {}
        self.calls = []

    def analyze(self, *, symbol, timeframe, limit, confirmed, filters_ok, decision_context=None):
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
    monitor = MarketTimeframeMonitor(path, analyzer, default_context=OWNER)

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
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER)
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
        default_context=OWNER,
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
    latest = monitor.latest_results(limit=1)
    assert latest[0]["symbol"] == "EURUSD"
    assert latest[0]["timeframe"] == "5m"
    assert latest[0]["result"]["signal"] == "COMPRA"


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



def test_monitor_latest_results_rejects_invalid_limits(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer())
    for limit in (0, 201, True):
        try:
            monitor.latest_results(limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid result limit was accepted")



def test_monitor_caps_active_subscriptions(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer())
    for index in range(100):
        monitor.subscribe(f"SYM{index}", "M1")
    try:
        monitor.subscribe("EXTRA", "M1")
    except ValueError as exc:
        assert "100" in str(exc)
    else:
        raise AssertionError("monitor accepted more than 100 active subscriptions")



def test_subscriptions_and_results_are_isolated_by_tenant_and_subject(tmp_path):
    analyzer = FakeAnalyzer()
    monitor = MarketTimeframeMonitor(
        tmp_path / "monitor.sqlite3", analyzer, default_context=OWNER
    )
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    other_tenant = TenantContext("tenant-b", "alice")

    monitor.subscribe("EURUSD", "M5", context=alice)
    monitor.subscribe("GBPUSD", "M5", context=bob)
    monitor.subscribe("USDJPY", "M5", context=other_tenant)

    assert [x["symbol"] for x in monitor.subscriptions(alice)] == ["EURUSD"]
    assert [x["symbol"] for x in monitor.subscriptions(bob)] == ["GBPUSD"]
    assert [x["symbol"] for x in monitor.subscriptions(other_tenant)] == ["USDJPY"]
    assert monitor.unsubscribe("EURUSD", "M5", context=bob) is False
    assert monitor.unsubscribe("EURUSD", "M5", context=alice) is True
    assert [x["symbol"] for x in monitor.subscriptions(bob)] == ["GBPUSD"]


def test_monitor_requires_trusted_context_without_local_default(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "strict.sqlite3", FakeAnalyzer())
    try:
        monitor.subscribe("EURUSD", "M5")
    except PermissionError:
        pass
    else:
        raise AssertionError("unscoped market subscription was accepted")
