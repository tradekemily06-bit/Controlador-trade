from datetime import datetime, timezone

from integration.market_timeframe_monitor import MarketTimeframeMonitor
from security.tenant_context import TenantContext


OWNER = TenantContext(tenant_id="tenant-local", subject_id="owner-local")


class FakeAnalyzer:
    def __init__(self):
        self.results = {}
        self.calls = []

    def analyze(self, *, symbol, timeframe, limit, confirmed, filters_ok, decision_context=None):
        self.calls.append((symbol, timeframe, limit, confirmed, filters_ok, decision_context))
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

    restored = MarketTimeframeMonitor(path, analyzer, default_context=OWNER)
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
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", analyzer, default_context=OWNER)
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
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER)

    for symbol, timeframe in (("../EURUSD", "5m"), ("EURUSD", "M0")):
        try:
            monitor.subscribe(symbol, timeframe)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid watch subscription was accepted")


def test_monitor_can_disable_a_subscription(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER)
    monitor.subscribe("EURUSD", "M5")

    assert monitor.unsubscribe("EURUSD", "M5")
    assert not monitor.unsubscribe("EURUSD", "M5")
    assert monitor.status()["enabled"] == 0



def test_monitor_latest_results_rejects_invalid_limits(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER)
    for limit in (0, 201, True):
        try:
            monitor.latest_results(limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid result limit was accepted")



def test_monitor_caps_active_subscriptions(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER)
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
    analyzer.results["5m"] = analysis_result(
        datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc), signal="COMPRA"
    )
    monitor.run_once(now=datetime(2026, 9, 7, 10, 5, 5, tzinfo=timezone.utc))

    assert [x["symbol"] for x in monitor.subscriptions(alice)] == ["EURUSD"]
    assert [x["symbol"] for x in monitor.subscriptions(bob)] == ["GBPUSD"]
    assert [x["symbol"] for x in monitor.subscriptions(other_tenant)] == ["USDJPY"]
    assert monitor.unsubscribe("EURUSD", "M5", context=bob) is False
    assert monitor.unsubscribe("EURUSD", "M5", context=alice) is True
    assert [x["symbol"] for x in monitor.subscriptions(bob)] == ["GBPUSD"]
    assert [x["symbol"] for x in monitor.latest_results(context=alice)] == ["EURUSD"]
    assert [x["symbol"] for x in monitor.latest_results(context=bob)] == ["GBPUSD"]
    assert [x["symbol"] for x in monitor.latest_results(context=other_tenant)] == ["USDJPY"]
    assert all(call[-1] in {alice, bob, other_tenant} for call in analyzer.calls)



def test_legacy_single_user_rows_migrate_only_to_configured_local_owner(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE market_timeframe_watch (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL,
                last_processed_candle TEXT, last_signal TEXT,
                last_status TEXT NOT NULL DEFAULT 'WAITING', last_error TEXT,
                PRIMARY KEY(symbol, timeframe)
            )
        """)
        db.execute("""
            CREATE TABLE market_timeframe_results (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                candle_at TEXT NOT NULL, result_json TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                PRIMARY KEY(symbol, timeframe, candle_at)
            )
        """)
        db.execute(
            "INSERT INTO market_timeframe_watch(symbol,timeframe,enabled,created_at) VALUES(?,?,1,?)",
            ("EURUSD", "5m", 1.0),
        )
        db.execute(
            "INSERT INTO market_timeframe_results VALUES(?,?,?,?,?)",
            ("EURUSD", "5m", "2026-09-07T10:00:00+00:00", '{"signal":"COMPRA"}', 2.0),
        )

    monitor = MarketTimeframeMonitor(path, FakeAnalyzer(), default_context=OWNER)
    remote = TenantContext("tenant-remote", "alice")
    assert [item["symbol"] for item in monitor.subscriptions(OWNER)] == ["EURUSD"]
    assert [item["symbol"] for item in monitor.latest_results(context=OWNER)] == ["EURUSD"]
    assert monitor.subscriptions(remote) == []
    assert monitor.latest_results(context=remote) == []


def test_monitor_requires_trusted_context_without_local_default(tmp_path):
    monitor = MarketTimeframeMonitor(tmp_path / "strict.sqlite3", FakeAnalyzer())
    try:
        monitor.subscribe("EURUSD", "M5")
    except PermissionError:
        pass
    else:
        raise AssertionError("unscoped market subscription was accepted")



def test_monitor_stop_timeout_keeps_worker_visible_until_it_exits(tmp_path):
    import threading
    import time

    monitor = MarketTimeframeMonitor(
        tmp_path / "monitor.sqlite3", FakeAnalyzer(), default_context=OWNER
    )
    entered = threading.Event()
    release = threading.Event()

    def blocked_run_once():
        entered.set()
        release.wait(timeout=2)
        return []

    monitor.run_once = blocked_run_once
    monitor.start()
    assert entered.wait(timeout=1)

    monitor.stop(timeout=0.01)
    assert monitor.status()["worker_running"] is True
    first_thread = monitor._thread

    # Calling start while the original worker is still alive must not
    # create a duplicate polling loop.
    monitor.start()
    assert monitor._thread is first_thread

    release.set()
    monitor.stop(timeout=1)
    assert monitor.status()["worker_running"] is False
    assert monitor._thread is None



def test_monitor_uses_account_provider_clock_instead_of_device_clock(tmp_path):
    broker_now = datetime(2026, 11, 28, 13, 5, 5, tzinfo=timezone(__import__("datetime").timedelta(hours=3)))
    calls = []

    def broker_clock(context, symbol):
        calls.append((context, symbol))
        return broker_now

    analyzer = FakeAnalyzer()
    monitor = MarketTimeframeMonitor(
        tmp_path / "broker-clock.sqlite3",
        analyzer,
        default_context=OWNER,
        provider_clock=broker_clock,
    )
    monitor.subscribe("EURUSD", "M1")

    expected = monitor.expected_last_closed_candle(
        "M1",
        now=datetime(2035, 1, 1, tzinfo=timezone.utc),
        context=OWNER,
        symbol="EURUSD",
    )

    assert expected == datetime(2026, 11, 28, 10, 4, tzinfo=timezone.utc)
    assert calls == [(OWNER, "EURUSD")]
