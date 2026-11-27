from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest
import threading
import time

from integration.tenant_connection_timeframe_monitor import TenantConnectionTimeframeMonitor
from security.tenant_context import TenantContext


class Session:
    def __init__(self, provider_id, source, adapter=None):
        self.provider_id = provider_id
        self.source = source
        self.adapter = adapter


class Sessions:
    def __init__(self):
        self.items = {}

    def add(self, owner, connection_id, provider_id):
        self.items[(owner.tenant_id, owner.subject_id, connection_id)] = Session(provider_id, f"{provider_id}:{connection_id}")

    def get(self, owner, *, connection_id):
        return self.items.get((owner.tenant_id, owner.subject_id, connection_id))


class Analyzer:
    def __init__(self, candle_at, signal):
        self.candle_at = candle_at
        self.signal = signal
        self.calls = 0
        self.last_kwargs = None

    def analyze(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return {
            "signal": self.signal,
            "status": "ANALYZED",
            "market_data": {"last_candle_at": self.candle_at},
        }


def _id(char):
    return char * 32


def test_subscriptions_and_results_are_isolated_per_account(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    sessions.add(owner, _id("b"), "broker_b")
    analyzers = {}

    def factory(session, context):
        key = session.source
        if key not in analyzers:
            analyzers[key] = Analyzer(expected.isoformat(), "COMPRA" if "broker_a" in key else "VENDA")
        return analyzers[key]

    monitor = TenantConnectionTimeframeMonitor(tmp_path / "cycles.sqlite3", sessions, factory)
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = monitor.expected_last_closed_candle("M5", now)
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    monitor.subscribe(owner, _id("b"), "EURUSD", "M5")

    results = monitor.run_once(now=now)
    assert len(results) == 2
    assert {item["connection_id"] for item in results} == {_id("a"), _id("b")}
    assert {item["provider_id"] for item in results} == {"broker_a", "broker_b"}
    assert len(monitor.latest_results(owner, _id("a"), now=now)) == 1
    assert len(monitor.latest_results(owner, _id("b"), now=now)) == 1
    assert monitor.latest_results(owner, _id("a"), now=now)[0]["result"]["signal"] == "COMPRA"
    assert monitor.latest_results(owner, _id("b"), now=now)[0]["result"]["signal"] == "VENDA"



def test_latest_results_expires_signal_at_next_timeframe_close(tmp_path):
    owner = TenantContext("tenant-expiry", "alice")
    connection = _id("e")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "signal-expiry.sqlite3", sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "COMPRA"),
    )
    monitor.subscribe(owner, connection, "EURUSD", "M5")
    assert len(monitor.run_once(now=now)) == 1

    still_valid = monitor.latest_results(owner, connection, now=now)
    assert still_valid[0]["signal_valid"] is True
    assert still_valid[0]["signal_validity"] == "VALID"
    assert still_valid[0]["result"]["signal"] == "COMPRA"

    # At 12:11 the 12:05 M5 candle has closed. The old 12:00 signal
    # remains in history but must never be exposed as an active direction.
    expired_at = datetime(2026, 11, 27, 12, 11, tzinfo=timezone.utc)
    expired = monitor.latest_results(owner, connection, now=expired_at)
    assert expired[0]["signal_valid"] is False
    assert expired[0]["signal_validity"] == "EXPIRED"
    assert expired[0]["result"]["original_signal"] == "COMPRA"
    assert expired[0]["result"]["signal"] is None
    assert expired[0]["result"]["status"] == "SIGNAL_EXPIRED"




def test_next_closed_m1_candle_gets_a_new_market_decision(tmp_path):
    owner = TenantContext("tenant-continuous-m1", "alice")
    connection = _id("c")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    first_candle = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    second_candle = datetime(2026, 11, 27, 12, 1, tzinfo=timezone.utc)

    class ChangingMarket:
        calls = 0
        def analyze(self, **kwargs):
            self.calls += 1
            candle = first_candle if self.calls == 1 else second_candle
            signal = "COMPRA" if self.calls == 1 else "VENDA"
            return {
                "signal": signal,
                "status": "ANALYZED",
                "market_data": {"last_candle_at": candle.isoformat()},
            }

    analyzer = ChangingMarket()
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "continuous-m1.sqlite3",
        sessions,
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, connection, "EURUSD", "M1")

    first_cycle = datetime(2026, 11, 27, 12, 1, 6, tzinfo=timezone.utc)
    second_cycle = datetime(2026, 11, 27, 12, 2, 6, tzinfo=timezone.utc)
    assert len(monitor.run_once(now=first_cycle)) == 1
    assert len(monitor.run_once(now=second_cycle)) == 1
    assert analyzer.calls == 2

    history = monitor.latest_results(owner, connection, now=second_cycle)
    assert len(history) == 2
    current = next(item for item in history if item["candle_at"] == second_candle.isoformat())
    expired = next(item for item in history if item["candle_at"] == first_candle.isoformat())
    assert current["signal_valid"] is True
    assert current["result"]["signal"] == "VENDA"
    assert expired["signal_valid"] is False
    assert expired["result"]["signal"] is None
    assert expired["result"]["original_signal"] == "COMPRA"
    assert expired["result"]["status"] == "SIGNAL_EXPIRED"


@pytest.mark.parametrize(
    ("timeframe", "analysis_now", "expired_now", "candle_at"),
    [
        ("M1", "2026-11-27T12:01:06+00:00", "2026-11-27T12:02:06+00:00", "2026-11-27T12:00:00+00:00"),
        ("M5", "2026-11-27T12:06:06+00:00", "2026-11-27T12:11:06+00:00", "2026-11-27T12:00:00+00:00"),
        ("M15", "2026-11-27T12:16:06+00:00", "2026-11-27T12:31:06+00:00", "2026-11-27T12:00:00+00:00"),
    ],
)
def test_signal_expiry_tracks_selected_timeframe(
    tmp_path, timeframe, analysis_now, expired_now, candle_at
):
    owner = TenantContext(f"tenant-{timeframe.lower()}", "alice")
    connection = _id("d")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"expiry-{timeframe}.sqlite3", sessions,
        lambda _session, _context: Analyzer(candle_at, "VENDA"),
    )
    monitor.subscribe(owner, connection, "EURUSD", timeframe)
    assert len(monitor.run_once(now=datetime.fromisoformat(analysis_now))) == 1
    current = monitor.latest_results(
        owner, connection, now=datetime.fromisoformat(analysis_now)
    )
    assert current[0]["signal_valid"] is True
    assert current[0]["result"]["signal"] == "VENDA"

    expired = monitor.latest_results(
        owner, connection, now=datetime.fromisoformat(expired_now)
    )
    assert expired[0]["signal_valid"] is False
    assert expired[0]["result"]["signal"] is None
    assert expired[0]["result"]["original_signal"] == "VENDA"


def test_delayed_notification_is_downgraded_after_its_candle_expires(tmp_path):
    owner = TenantContext("tenant-delayed-alert", "alice")
    connection = _id("d")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime.now(timezone.utc)
    def unavailable_sink(_event):
        raise RuntimeError("temporary delivery outage")

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "delayed-notification.sqlite3", sessions,
        lambda _session, _context: Analyzer(
            monitor.expected_last_closed_candle("M5", now).isoformat(), "COMPRA"
        ),
        on_result=unavailable_sink,
    )
    monitor.subscribe(owner, connection, "EURUSD", "M5")
    assert len(monitor.run_once(now=now)) == 1
    with monitor._connect() as db:
        db.execute(
            "UPDATE tenant_connection_notification_outbox SET candle_at=?, lease_until=NULL",
            ((monitor.expected_last_closed_candle("M5", now) - timedelta(minutes=5)).isoformat(),),
        )
    delivered = []
    monitor.on_result = delivered.append
    assert monitor.dispatch_pending_notifications() == 1
    assert delivered[0]["result"]["signal"] is None
    assert delivered[0]["result"]["original_signal"] == "COMPRA"
    assert delivered[0]["result"]["status"] == "SIGNAL_EXPIRED"


def test_other_tenant_cannot_list_or_unsubscribe_account_watch(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    other = TenantContext("tenant-b", "bob")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "cycles.sqlite3", sessions,
        lambda session, context: Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR"),
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    assert monitor.subscriptions(other) == []
    assert monitor.unsubscribe(other, _id("a"), "EURUSD", "M5") is False
    assert len(monitor.subscriptions(owner)) == 1


def test_stale_or_unclosed_candle_is_not_published_or_marked_processed(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    emitted = []
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "cycles.sqlite3", sessions,
        lambda session, context: Analyzer("2026-11-27T11:55:00+00:00", "COMPRA"),
        on_result=emitted.append,
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    assert monitor.run_once(now=now) == []
    assert emitted == []
    assert monitor.subscriptions(owner)[0]["last_status"] == "WAITING_FOR_CLOSED_CANDLE"


def test_missing_adapter_marks_data_unavailable_without_signal(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "cycles.sqlite3", sessions,
        lambda session, context: Analyzer("2026-11-27T12:00:00+00:00", "COMPRA"),
    )
    # Subscribe while the adapter is verified, then simulate its disconnection.
    sessions.add(owner, _id("a"), "broker_a")
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    sessions.items.clear()
    monitor.run_once(now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc))
    row = monitor.subscriptions(owner)[0]
    assert row["last_status"] == "DATA_UNAVAILABLE"
    assert row["last_signal"] is None


def test_provider_exception_details_are_not_persisted_in_watch_status(tmp_path):
    owner = TenantContext("tenant-error-safety", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    secret_detail = "authorization=Bearer-super-secret-value"

    def fail_analysis(_session, _context):
        raise RuntimeError(secret_detail)

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "sanitized-provider-errors.sqlite3",
        sessions,
        fail_analysis,
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    monitor.run_once(now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc))

    watch = monitor.subscriptions(owner)[0]
    assert watch["last_status"] == "DATA_UNAVAILABLE"
    assert watch["last_error"] == "RuntimeError"
    assert secret_detail not in str(watch)

def test_repeated_poll_does_not_process_same_closed_candle_twice(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    calls = []
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "cycles.sqlite3", sessions,
        lambda session, context: Analyzer(monitor.expected_last_closed_candle("M5", now).isoformat(), "AGUARDAR"),
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    assert len(monitor.run_once(now=now)) == 1
    assert monitor.run_once(now=now) == []


def test_slow_account_does_not_serialize_other_account_cycles(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    sessions.add(owner, _id("b"), "broker_b")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    barrier = threading.Barrier(2)
    expected = "2026-11-27T12:00:00+00:00"

    class ConcurrentAnalyzer:
        def analyze(self, **kwargs):
            barrier.wait(timeout=3)
            return {
                "signal": "AGUARDAR",
                "status": "ANALYZED",
                "market_data": {"last_candle_at": expected},
            }

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "cycles.sqlite3", sessions,
        lambda session, context: ConcurrentAnalyzer(),
        max_workers=2,
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    monitor.subscribe(owner, _id("b"), "EURUSD", "M5")
    results = monitor.run_once(now=now)
    assert len(results) == 2


def test_live_closed_candle_stream_gates_account_timeframe_analysis(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    class StreamAdapter:
        account_id = 123
        def __init__(self):
            self.callback = None
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.callback = None

    adapter = StreamAdapter()
    session = Session("ctrader_open_api", "ctrader:123", adapter)
    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected.isoformat(), "AGUARDAR")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "live-stream.sqlite3", Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("c"), "EURUSD", "M5")
    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0
    assert monitor.subscriptions(owner)[0]["last_status"] == "WAITING_FOR_LIVE_CLOSED_CANDLE"

    candle = SimpleNamespace(
        timestamp=expected,
        is_valid=lambda: True,
    )
    adapter.callback({
        "account_id": 123, "symbol": "EURUSD", "timeframe": "M5",
        "candle": candle, "closed": True,
    })
    results = monitor.run_once(now=now)
    assert len(results) == 1
    assert analyzer.calls == 1
    assert analyzer.last_kwargs["live_candle"] is candle
    assert results[0]["candle_at"] == expected.isoformat()


def test_live_stream_rejects_wrong_account_and_unclosed_candles(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    class StreamAdapter:
        account_id = 456
        def subscribe_live_candles(self, symbol, timeframe, callback): self.callback = callback
    adapter = StreamAdapter()
    session = Session("ctrader_open_api", "ctrader:456", adapter)
    class Registry:
        def get(self, context, *, connection_id): return session
    analyzer = Analyzer(expected.isoformat(), "AGUARDAR")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "live-stream-isolation.sqlite3", Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("d"), "EURUSD", "M5")
    candle = SimpleNamespace(timestamp=expected, is_valid=lambda: True)
    adapter.callback({"account_id": 999, "symbol": "EURUSD", "timeframe": "5m", "candle": candle, "closed": True})
    adapter.callback({"account_id": 456, "symbol": "EURUSD", "timeframe": "5m", "candle": candle, "closed": False})
    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0


def test_live_stream_rebinds_when_provider_adapter_instance_changes(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)

    class Adapter:
        account_id = 789
        def __init__(self):
            self.callback = None
            self.unsubscribed = False
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.unsubscribed = True

    first, second = Adapter(), Adapter()
    class Registry:
        session = Session("ctrader_open_api", "ctrader:789", first)
        def get(self, context, *, connection_id):
            return self.session if context == owner else None

    registry = Registry()
    analyzer = Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "stream-rebind.sqlite3", registry,
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("e"), "EURUSD", "M5")
    assert first.callback is not None

    registry.session = Session("ctrader_open_api", "ctrader:789", second)
    assert monitor.run_once(now=now) == []
    assert first.unsubscribed is True
    assert second.callback is not None
    assert monitor.status(owner)["live_streams"] == 1

    candle_at = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    stale_candle = SimpleNamespace(timestamp=candle_at, is_valid=lambda: True)
    fresh_candle = SimpleNamespace(timestamp=candle_at, is_valid=lambda: True)
    event = {"account_id": 789, "symbol": "EURUSD", "timeframe": "5m", "closed": True}
    first.callback({**event, "candle": stale_candle})
    key = (owner.tenant_id, owner.subject_id, _id("e"), "EURUSD", "5m")
    assert key not in monitor._live_candles
    second.callback({**event, "candle": fresh_candle})
    assert monitor._live_candles[key] is fresh_candle


def test_disconnected_stream_provider_reconnects_before_subscribing(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    class Adapter:
        account_id = 321
        def __init__(self):
            self.connected = False
            self.reconnect_calls = 0
            self.callback = None
        def status(self):
            return {"connected": self.connected}
        def reconnect(self):
            self.reconnect_calls += 1
            self.connected = True
            return {"account_mode": "DEMO"}
        def subscribe_live_candles(self, symbol, timeframe, callback):
            assert self.connected is True
            self.callback = callback
    adapter = Adapter()
    session = Session("ctrader_open_api", "ctrader:321", adapter)
    class Registry:
        def get(self, context, *, connection_id): return session
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "reconnect-before-subscribe.sqlite3", Registry(),
        lambda _session, _context: Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR"),
    )
    result = monitor.subscribe(owner, _id("f"), "EURUSD", "M5")
    assert adapter.reconnect_calls == 1
    assert adapter.callback is not None
    assert result["live_candle_stream"] == "BOUND"


def test_stream_capable_disconnected_provider_fails_closed_without_reconnect(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    class Adapter:
        account_id = 654
        def status(self): return {"connected": False}
        def subscribe_live_candles(self, symbol, timeframe, callback):
            raise RuntimeError("offline")
    session = Session("ctrader_open_api", "ctrader:654", Adapter())
    class Registry:
        def get(self, context, *, connection_id): return session
    analyzer = Analyzer("2026-11-27T12:00:00+00:00", "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "stream-fail-closed.sqlite3", Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("1"), "EURUSD", "M5")
    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0
    assert monitor.subscriptions(owner)[0]["last_status"] == "LIVE_STREAM_UNAVAILABLE"


def test_live_stream_candle_reaches_real_standalone_analysis_and_persisted_result(tmp_path):
    from datetime import timedelta
    from core.unified_intelligence import UnifiedIntelligence
    from data.models import Candle
    from integration.standalone_market_analysis import StandaloneMarketAnalysisService

    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    history_start = expected - timedelta(minutes=35)
    history = []
    for index in range(8):
        stamp = history_start + timedelta(minutes=5 * index)
        base = 1.1000 + index * 0.0001
        history.append(Candle(stamp, base, base + 0.0003, base - 0.0002, base + 0.0001, 100 + index))

    class StreamingProvider:
        account_id = 321
        def __init__(self):
            self.callback = None
        def fetch(self, request):
            return tuple(history[-request.limit:])
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.callback = None

    adapter = StreamingProvider()
    session = Session("ctrader_open_api", "ctrader:321", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    emitted = []
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "live-to-analysis.sqlite3",
        Registry(),
        lambda current_session, _context: StandaloneMarketAnalysisService(
            provider=current_session.adapter,
            source="ctrader:321",
            intelligence=UnifiedIntelligence(),
        ),
        on_result=emitted.append,
    )
    monitor.subscribe(owner, _id("9"), "EURUSD", "5m")
    live = Candle(expected, 1.1009, 1.1014, 1.1007, 1.1012, 250)
    adapter.callback({
        "account_id": 321, "symbol": "EURUSD", "timeframe": "5m",
        "candle": live, "closed": True,
    })

    results = monitor.run_once(now=now)
    assert len(results) == 1
    analyzed = results[0]["result"]
    assert analyzed["market_data"]["last_candle_at"] == expected.isoformat()
    assert analyzed["market_data"]["ohlcv"][-1]["timestamp"] == expected.isoformat()
    assert analyzed["market_data"]["ohlcv"][-1]["close"] == live.close
    assert analyzed["market_data"]["ohlcv"][-1]["volume"] == live.volume
    persisted = monitor.latest_results(owner, _id("9"))
    assert len(persisted) == 1
    assert persisted[0]["result"]["market_data"]["ohlcv"][-1]["close"] == live.close
    assert emitted[0]["result"]["market_data"]["ohlcv"][-1]["close"] == live.close
    assert analyzed["execution_authorized"] is False


def test_notification_failure_does_not_discard_durable_analysis(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("2"), "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    def broken_notification(_event):
        raise RuntimeError("push provider temporarily unavailable")

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-isolation.sqlite3",
        sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=broken_notification,
    )
    monitor.subscribe(owner, _id("2"), "EURUSD", "5m")

    results = monitor.run_once(now=now)

    assert len(results) == 1
    saved = monitor.latest_results(owner, _id("2"), now=now)
    assert len(saved) == 1
    assert saved[0]["result"]["signal"] == "AGUARDAR"
    watch = monitor.subscriptions(owner)[0]
    assert watch["last_processed_candle"] == expected.isoformat()
    assert watch["last_status"] == "ANALYZED"
    assert watch["last_error"] is None


def test_status_live_stream_counters_are_isolated_by_tenant_and_subject(tmp_path):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "tenant-status-isolation.sqlite3", Sessions(),
        lambda session, owner: None,
    )
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-b", "bob")
    alice_key = (alice.tenant_id, alice.subject_id, "a" * 32, "EURUSD", "5m")
    bob_key = (bob.tenant_id, bob.subject_id, "b" * 32, "GBPUSD", "1m")
    with monitor._lock:
        monitor._live_streams.update({alice_key, bob_key})
        monitor._live_stream_adapters.update({alice_key: object(), bob_key: object()})
        monitor._live_candles.update({alice_key: object(), bob_key: object()})
        monitor._worker_error = "ProviderFailure"
    alice_status = monitor.status(alice)
    bob_status = monitor.status(bob)
    operator_status = monitor.status()
    assert alice_status["live_streams"] == 1
    assert alice_status["buffered_live_candles"] == 1
    assert alice_status["live_stream_adapter_bindings"] == 1
    assert alice_status["worker_error_class"] is None
    assert bob_status["live_streams"] == 1
    assert bob_status["buffered_live_candles"] == 1
    assert operator_status["live_streams"] == 2
    assert operator_status["worker_error_class"] == "ProviderFailure"


def test_subscription_diagnostics_distinguish_disconnected_waiting_and_fresh(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-a", "alice")
    connection = _id("7")
    now = datetime.now(timezone.utc)
    class Adapter:
        account_id = 700
        def __init__(self, connected=True):
            self.connected = connected
        def status(self):
            return {"connected": self.connected}
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback

    adapter = Adapter()
    session = Session("ctrader_open_api", "ctrader:700", adapter)
    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "freshness-diagnostics.sqlite3", Registry(),
        lambda _session, _context: Analyzer(now.isoformat(), "AGUARDAR"),
    )
    monitor.subscribe(owner, connection, "EURUSD", "M5")
    row = monitor.subscriptions(owner)[0]
    assert row["adapter_status"] == "CONNECTED"
    assert row["data_freshness_state"] == "WAITING_FOR_CANDLE"
    assert row["expected_last_closed_candle_at"]

    expected = monitor.expected_last_closed_candle("5m", datetime.now(timezone.utc))
    candle = SimpleNamespace(timestamp=expected, is_valid=lambda: True)
    adapter.callback({
        "account_id": 700, "symbol": "EURUSD", "timeframe": "5m",
        "candle": candle, "closed": True,
    })
    row = monitor.subscriptions(owner)[0]
    assert row["data_freshness_state"] == "FRESH"
    assert row["live_candle_age_seconds"] is not None

    adapter.connected = False
    row = monitor.subscriptions(owner)[0]
    assert row["adapter_status"] == "DISCONNECTED"
    assert row["data_freshness_state"] == "DISCONNECTED"


def test_concurrent_cycle_ticks_do_not_duplicate_analysis_or_notifications(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("c")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    entered = threading.Event()
    release = threading.Event()
    emitted = []

    class SlowAnalyzer:
        calls = 0
        def analyze(self, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(3)
            return {
                "signal": "AGUARDAR", "status": "ANALYZED",
                "market_data": {"last_candle_at": expected.isoformat()},
            }

    analyzer = SlowAnalyzer()
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "concurrent-cycle.sqlite3", sessions,
        lambda _session, _context: analyzer, on_result=emitted.append,
    )
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    first_result = []
    first = threading.Thread(target=lambda: first_result.extend(monitor.run_once(now=now)))
    first.start()
    assert entered.wait(2)

    # A second scheduler tick overlaps the first one for the same watch.
    second_result = monitor.run_once(now=now)
    release.set()
    first.join(3)

    assert not first.is_alive()
    assert len(first_result) == 1
    assert second_result == []
    assert analyzer.calls == 1
    assert len(emitted) == 1
    assert len(monitor.latest_results(owner, connection)) == 1


def test_notification_outbox_retries_with_stable_event_id_after_sink_failure(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("d")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    calls = []

    def flaky_sink(event):
        calls.append(event)
        if len(calls) == 1:
            raise RuntimeError("push temporarily unavailable")

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-outbox.sqlite3", sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=flaky_sink,
    )
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    assert len(monitor.run_once(now=now)) == 1
    assert len(calls) == 1

    with monitor._connect() as db:
        pending = db.execute("""
            SELECT event_id, attempts, delivered_at
            FROM tenant_connection_notification_outbox
        """).fetchone()
        assert pending is not None
        assert pending["attempts"] == 1
        assert pending["delivered_at"] is None
        db.execute("""
            UPDATE tenant_connection_notification_outbox
            SET lease_until=0 WHERE event_id=?
        """, (pending["event_id"],))

    assert monitor.dispatch_pending_notifications() == 1
    assert len(calls) == 2
    assert calls[0]["event_id"] == calls[1]["event_id"]
    assert calls[1]["provider_id"] == "broker_a"
    with monitor._connect() as db:
        delivered = db.execute("""
            SELECT delivered_at, attempts
            FROM tenant_connection_notification_outbox
            WHERE event_id=?
        """, (pending["event_id"],)).fetchone()
    assert delivered["delivered_at"] is not None
    assert delivered["attempts"] == 2


def test_reconnect_is_serialized_for_timeframes_sharing_one_account_adapter(tmp_path):
    import time

    owner = TenantContext("tenant-a", "alice")
    connection = _id("e")

    class ReconnectingAdapter:
        account_id = 700
        def __init__(self):
            self.connected = False
            self.reconnect_calls = 0
            self.subscriptions = []
        def status(self):
            return {"connected": self.connected}
        def reconnect(self):
            self.reconnect_calls += 1
            time.sleep(0.05)
            self.connected = True
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.subscriptions.append((symbol, timeframe, callback))

    adapter = ReconnectingAdapter()
    session = Session("ctrader_open_api", "ctrader:700", adapter)
    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner and connection_id == connection else None

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "serialized-reconnect.sqlite3", Registry(),
        lambda _session, _owner: None,
    )
    outcomes = []
    threads = [
        threading.Thread(target=lambda tf=tf: outcomes.append(
            monitor._ensure_live_stream(owner, session, connection, "EURUSD", tf)
        ))
        for tf in ("1m", "5m", "15m", "1h")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)

    assert all(not thread.is_alive() for thread in threads)
    assert outcomes == [True] * 4
    assert adapter.reconnect_calls == 1
    assert len(adapter.subscriptions) == 4


def test_processing_lease_prevents_duplicate_work_across_monitor_instances(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("f")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    entered = threading.Event()
    release = threading.Event()

    class SlowAnalyzer:
        calls = 0
        def analyze(self, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(3)
            return {
                "signal": "AGUARDAR", "status": "ANALYZED",
                "market_data": {"last_candle_at": expected.isoformat()},
            }

    analyzer = SlowAnalyzer()
    db_path = tmp_path / "cross-process-lease.sqlite3"
    first = TenantConnectionTimeframeMonitor(
        db_path, sessions, lambda _session, _context: analyzer,
    )
    second = TenantConnectionTimeframeMonitor(
        db_path, sessions, lambda _session, _context: analyzer,
    )
    first.subscribe(owner, connection, "EURUSD", "5m")
    first_result = []
    worker = threading.Thread(target=lambda: first_result.extend(first.run_once(now=now)))
    worker.start()
    assert entered.wait(2)

    # A second monitor object represents another worker sharing the database.
    assert second.run_once(now=now) == []
    release.set()
    worker.join(3)

    assert not worker.is_alive()
    assert len(first_result) == 1
    assert analyzer.calls == 1
    assert len(first.latest_results(owner, connection)) == 1


def test_processing_lease_renewal_requires_current_owner_and_unexpired_lease(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "lease-renewal.sqlite3", Sessions(),
        lambda _session, _context: None,
    )
    row = {
        "tenant_id": owner.tenant_id, "subject_id": owner.subject_id,
        "connection_id": _id("a"), "symbol": "EURUSD", "timeframe": "5m",
    }
    lease = monitor._acquire_processing_lease(row, lease_seconds=30)
    assert lease is not None
    assert monitor._renew_processing_lease(lease, lease_seconds=60) is True
    assert monitor._renew_processing_lease(("wrong-key", "wrong-token")) is False
    monitor._release_processing_lease(lease)
    assert monitor._renew_processing_lease(lease) is False


def test_expired_or_replaced_processing_lease_cannot_persist_analysis(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("b")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    emitted = []
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "lease-fencing.sqlite3", sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=emitted.append,
    )
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    with monitor._connect() as db:
        row = dict(db.execute("""
            SELECT tenant_id, subject_id, connection_id, symbol, timeframe,
                   last_processed_candle, last_signal
            FROM tenant_connection_timeframe_watch
        """).fetchone())
    stale_lease = monitor._acquire_processing_lease(row)
    assert stale_lease is not None

    # Simulate lease expiry and a different worker taking ownership.
    with monitor._connect() as db:
        db.execute("""
            UPDATE tenant_connection_timeframe_processing_lease
            SET owner_token=?, expires_at=?
            WHERE lease_key=?
        """, ("new-owner-token", time.time() + 300, stale_lease[0]))

    result = monitor._process_claimed(
        row, now, processing_lease=stale_lease,
    )
    assert result is None
    assert monitor.latest_results(owner, connection) == []
    assert emitted == []



def test_worker_losing_lease_during_analysis_is_fenced_before_persistence(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("c")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    entered = threading.Event()
    release_analysis = threading.Event()
    emitted = []

    class SlowAnalyzer:
        def analyze(self, **kwargs):
            entered.set()
            assert release_analysis.wait(3)
            return {
                "signal": "AGUARDAR", "status": "ANALYZED",
                "market_data": {"last_candle_at": expected.isoformat()},
            }

    db_path = tmp_path / "mid-analysis-lease-fencing.sqlite3"
    first = TenantConnectionTimeframeMonitor(
        db_path, sessions, lambda _session, _context: SlowAnalyzer(),
        on_result=emitted.append,
    )
    second = TenantConnectionTimeframeMonitor(
        db_path, sessions, lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
    )
    first.subscribe(owner, connection, "EURUSD", "5m")
    with first._connect() as db:
        row = dict(db.execute("""
            SELECT tenant_id, subject_id, connection_id, symbol, timeframe,
                   last_processed_candle, last_signal
            FROM tenant_connection_timeframe_watch
        """).fetchone())

    first_result = []
    worker = threading.Thread(target=lambda: first_result.extend(first.run_once(now=now)))
    worker.start()
    assert entered.wait(2)

    # Expire the first worker's lease while its provider analysis is in flight.
    first_lease_key = first._processing_lease_key(row)
    with first._connect() as db:
        db.execute("""
            UPDATE tenant_connection_timeframe_processing_lease
            SET expires_at=0 WHERE lease_key=?
        """, (first_lease_key,))

    replacement_lease = second._acquire_processing_lease(row, lease_seconds=300)
    assert replacement_lease is not None
    assert replacement_lease[0] == first_lease_key

    # The old worker finishes after ownership has changed. Its final DB fence
    # must reject both the analysis result and its notification event.
    release_analysis.set()
    worker.join(3)
    assert not worker.is_alive()
    assert first_result == []
    assert first.latest_results(owner, connection) == []
    assert emitted == []

    with first._connect() as db:
        current = db.execute("""
            SELECT owner_token FROM tenant_connection_timeframe_processing_lease
            WHERE lease_key=?
        """, (first_lease_key,)).fetchone()
    assert current is not None
    assert current["owner_token"] == replacement_lease[1]
    second._release_processing_lease(replacement_lease)

def test_expired_notification_worker_cannot_ack_after_outbox_reclaim(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("e")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def sink(event):
        calls.append(event["event_id"])
        if len(calls) == 1:
            raise RuntimeError("initial delivery fails")
        if len(calls) == 2:
            entered.set()
            assert release.wait(3)
            return
        raise RuntimeError("reclaimed owner leaves event pending")

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-lease-fence.sqlite3", sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=sink,
    )
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    assert len(monitor.run_once(now=now)) == 1
    with monitor._connect() as db:
        row = db.execute(
            "SELECT event_id FROM tenant_connection_notification_outbox"
        ).fetchone()
        assert row is not None
        db.execute(
            "UPDATE tenant_connection_notification_outbox SET lease_until=0 WHERE event_id=?",
            (row["event_id"],),
        )

    first = threading.Thread(target=monitor.dispatch_pending_notifications)
    first.start()
    assert entered.wait(3)
    with monitor._connect() as db:
        db.execute(
            "UPDATE tenant_connection_notification_outbox SET lease_until=0 WHERE event_id=?",
            (row["event_id"],),
        )

    assert monitor.dispatch_pending_notifications() == 0
    with monitor._connect() as db:
        reclaimed = db.execute(
            "SELECT lease_token, lease_until, delivered_at, dead_at "
            "FROM tenant_connection_notification_outbox WHERE event_id=?",
            (row["event_id"],),
        ).fetchone()
        # The reclaimed owner also failed; it released its lease into backoff.
        assert reclaimed["lease_token"] is None
        assert reclaimed["lease_until"] is not None
        assert reclaimed["delivered_at"] is None
        assert reclaimed["dead_at"] is None

    release.set()
    first.join(3)
    assert not first.is_alive()
    with monitor._connect() as db:
        final = db.execute(
            "SELECT lease_token, delivered_at FROM tenant_connection_notification_outbox WHERE event_id=?",
            (row["event_id"],),
        ).fetchone()
    assert final["lease_token"] is None
    assert final["delivered_at"] is None
    assert calls == [row["event_id"], row["event_id"], row["event_id"]]

def test_expired_notification_lease_is_not_counted_as_delivered(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("f")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    holder = {}

    def sink(event):
        monitor = holder["monitor"]
        with monitor._connect() as db:
            db.execute(
                "UPDATE tenant_connection_notification_outbox "
                "SET lease_until=0 WHERE event_id=?",
                (event["event_id"],),
            )

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-expired-ack.sqlite3", sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=sink,
    )
    holder["monitor"] = monitor
    monitor.subscribe(owner, connection, "EURUSD", "5m")

    # The callback succeeds, but expires its lease before durable acknowledgement.
    assert len(monitor.run_once(now=now)) == 1
    assert monitor.dispatch_pending_notifications() == 0
    with monitor._connect() as db:
        row = db.execute(
            "SELECT delivered_at FROM tenant_connection_notification_outbox"
        ).fetchone()
    assert row["delivered_at"] is None



def test_tenant_notification_outbox_dead_letters_after_bounded_attempts(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    connection = _id("b")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    calls = []

    def failing_sink(event):
        calls.append(event["event_id"])
        raise RuntimeError("sensitive provider detail must not be persisted")

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-dead-letter.sqlite3",
        sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "AGUARDAR"),
        on_result=failing_sink,
        max_notification_attempts=2,
    )
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    assert len(monitor.run_once(now=now)) == 1

    with monitor._connect() as db:
        row = db.execute(
            "SELECT event_id, attempts, dead_at, last_error "
            "FROM tenant_connection_notification_outbox"
        ).fetchone()
        assert row["attempts"] == 1
        assert row["dead_at"] is None
        assert row["last_error"] == "RuntimeError"
        db.execute(
            "UPDATE tenant_connection_notification_outbox SET lease_until=0 WHERE event_id=?",
            (row["event_id"],),
        )

    assert monitor.dispatch_pending_notifications() == 0
    with monitor._connect() as db:
        dead = db.execute(
            "SELECT attempts, dead_at, lease_token, last_error "
            "FROM tenant_connection_notification_outbox WHERE event_id=?",
            (row["event_id"],),
        ).fetchone()
    assert dead["attempts"] == 2
    assert dead["dead_at"] is not None
    assert dead["lease_token"] is None
    assert dead["last_error"] == "RuntimeError"
    assert "sensitive provider detail" not in dead["last_error"]
    tenant_status = monitor.status(owner)
    assert tenant_status["notification_outbox_pending"] == 0
    assert tenant_status["notification_outbox_dead_lettered"] == 1
    other_tenant_status = monitor.status(TenantContext("tenant-b", "bob"))
    assert other_tenant_status["notification_outbox_dead_lettered"] == 0
    assert monitor.dispatch_pending_notifications() == 0
    assert calls == [row["event_id"], row["event_id"]]



def test_persisted_watch_rebinds_live_stream_after_monitor_restart(tmp_path):
    from datetime import datetime, timezone

    owner = TenantContext("tenant-restart", "alice")
    connection_id = _id("b")
    database = tmp_path / "restart-recovery.sqlite3"

    class StreamAdapter:
        account_id = 987
        def __init__(self):
            self.callback = None
            self.subscribe_calls = 0
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.subscribe_calls += 1
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.callback = None

    adapter_before_restart = StreamAdapter()
    adapter_after_restart = StreamAdapter()

    class Registry:
        adapter = adapter_before_restart
        def get(self, context, *, connection_id):
            if context != owner or connection_id != _id("b"):
                return None
            return Session("ctrader_open_api", "ctrader:987", self.adapter)

    registry = Registry()
    analyzer_calls = []

    class RestartAnalyzer:
        def analyze(self, **kwargs):
            analyzer_calls.append(kwargs)
            return {
                "signal": "AGUARDAR",
                "status": "ANALYZED",
                "market_data": {"last_candle_at": "2026-11-27T12:00:00+00:00"},
            }

    first = TenantConnectionTimeframeMonitor(
        database, registry, lambda _session, _context: RestartAnalyzer()
    )
    first.subscribe(owner, connection_id, "EURUSD", "M5")
    assert adapter_before_restart.callback is not None
    first.stop()

    # Simulate process restart: in-memory streams disappear, but the durable
    # watch remains and the new provider session is rebound from its registry.
    registry.adapter = adapter_after_restart
    restarted = TenantConnectionTimeframeMonitor(
        database, registry, lambda _session, _context: RestartAnalyzer()
    )

    assert len(restarted.subscriptions(owner)) == 1
    restarted.run_once(now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc))

    assert adapter_after_restart.subscribe_calls == 1
    assert adapter_after_restart.callback is not None
    assert restarted.status(owner)["live_streams"] == 1
    assert analyzer_calls == []
    assert restarted.subscriptions(owner)[0]["last_status"] == "WAITING_FOR_LIVE_CLOSED_CANDLE"
    restarted.stop()


def test_pending_notification_is_delivered_after_monitor_restart(tmp_path):
    owner = TenantContext("tenant-restart", "alice")
    connection = _id("c")
    sessions = Sessions()
    sessions.add(owner, connection, "broker_a")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    database = tmp_path / "notification-restart.sqlite3"
    failed_events = []

    def unavailable_sink(event):
        failed_events.append(event["event_id"])
        raise RuntimeError("temporary delivery outage")

    first = TenantConnectionTimeframeMonitor(
        database, sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "COMPRA"),
        on_result=unavailable_sink,
    )
    first.subscribe(owner, connection, "EURUSD", "5m")
    assert len(first.run_once(now=now)) == 1
    assert len(failed_events) == 1

    with first._connect() as db:
        pending = db.execute(
            "SELECT event_id, delivered_at FROM tenant_connection_notification_outbox"
        ).fetchone()
        assert pending is not None
        assert pending["delivered_at"] is None
        # Simulate restart after the failed worker's retry lease expires.
        db.execute(
            "UPDATE tenant_connection_notification_outbox "
            "SET lease_until=0 WHERE event_id=?",
            (pending["event_id"],),
        )
    first.stop()

    delivered = []
    restarted = TenantConnectionTimeframeMonitor(
        database, sessions,
        lambda _session, _context: Analyzer(expected.isoformat(), "COMPRA"),
        on_result=delivered.append,
    )
    assert restarted.dispatch_pending_notifications() == 1
    assert len(delivered) == 1
    assert delivered[0]["event_id"] == pending["event_id"]
    assert delivered[0]["tenant_context"] == owner

    with restarted._connect() as db:
        final = db.execute(
            "SELECT delivered_at, lease_token FROM tenant_connection_notification_outbox "
            "WHERE event_id=?",
            (pending["event_id"],),
        ).fetchone()
    assert final["delivered_at"] is not None
    assert final["lease_token"] is None
    first.stop()
    restarted.stop()


def test_live_stream_rejects_missing_account_identity(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-stream-no-account", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    class UnboundStreamAdapter:
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback

    adapter = UnboundStreamAdapter()
    session = Session("unknown_stream_provider", "unbound", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected.isoformat(), "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "stream-missing-account.sqlite3",
        Registry(),
        lambda _session, _context: analyzer,
    )
    subscription = monitor.subscribe(owner, _id("a"), "EURUSD", "M5")

    # Missing adapter identity is rejected before the monitor advertises a
    # bound stream; no callback can be registered as a false-positive bind.
    assert subscription["live_candle_stream"] == "NOT_SUPPORTED_OR_UNAVAILABLE"
    assert not hasattr(adapter, "callback")
    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0
    assert monitor.subscriptions(owner)[0]["last_status"] == "LIVE_STREAM_UNAVAILABLE"


def test_old_callback_cannot_reenter_after_unsubscribe_and_resubscribe_same_adapter(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-stream-generation", "alice")
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    class Adapter:
        account_id = 987
        def __init__(self):
            self.callbacks = []
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callbacks.append(callback)
        def unsubscribe_live_candles(self, symbol, timeframe):
            pass

    adapter = Adapter()
    session = Session("ctrader_open_api", "ctrader:987", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "stream-generation.sqlite3",
        Registry(),
        lambda _session, _context: Analyzer(expected.isoformat(), "COMPRA"),
    )
    connection = _id("d")
    monitor.subscribe(owner, connection, "EURUSD", "M5")
    old_callback = adapter.callbacks[-1]
    assert monitor.unsubscribe(owner, connection, "EURUSD", "M5") is True
    monitor.subscribe(owner, connection, "EURUSD", "M5")
    new_callback = adapter.callbacks[-1]
    assert new_callback is not old_callback

    stale_candle = SimpleNamespace(timestamp=expected, is_valid=lambda: True)
    current_candle = SimpleNamespace(timestamp=expected, is_valid=lambda: True)
    event = {"account_id": 987, "symbol": "EURUSD", "timeframe": "M5", "closed": True}
    old_callback({**event, "candle": stale_candle})
    key = (owner.tenant_id, owner.subject_id, connection, "EURUSD", "5m")
    assert key not in monitor._live_candles

    new_callback({**event, "candle": current_candle})
    assert monitor._live_candles[key] is current_candle

    # A late event from the old callback must not overwrite the current
    # binding's accepted candle after the new subscription is active.
    later_stale_candle = SimpleNamespace(
        timestamp=expected + timedelta(minutes=5), is_valid=lambda: True
    )
    old_callback({**event, "candle": later_stale_candle})
    assert monitor._live_candles[key] is current_candle


def test_live_stream_rejects_boolean_account_id_that_equals_integer_one(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-stream-typed-account", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    class Adapter:
        account_id = 1
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback

    adapter = Adapter()
    session = Session("ctrader_open_api", "ctrader:1", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected.isoformat(), "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "stream-typed-account.sqlite3",
        Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("b"), "EURUSD", "M5")
    candle = SimpleNamespace(timestamp=expected, is_valid=lambda: True)
    adapter.callback({
        "account_id": True,
        "symbol": "EURUSD",
        "timeframe": "M5",
        "candle": candle,
        "closed": True,
    })

    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0


@pytest.mark.parametrize(
    "lease_seconds",
    [True, 0, -1, float("nan"), float("inf"), float("-inf"), 10**1000, "30", None],
)
def test_notification_dispatch_rejects_invalid_lease_duration(tmp_path, lease_seconds):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "invalid-notification-lease.sqlite3",
        Sessions(),
        lambda _session, _context: None,
        on_result=lambda _event: None,
    )
    with pytest.raises(ValueError, match="lease_seconds"):
        monitor.dispatch_pending_notifications(lease_seconds=lease_seconds)

def test_notification_dispatch_validates_arguments_without_sink(tmp_path):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-no-sink.sqlite3",
        Sessions(),
        lambda _session, _context: None,
    )
    with pytest.raises(ValueError, match="lease_seconds"):
        monitor.dispatch_pending_notifications(lease_seconds=10**1000)
    with pytest.raises(ValueError, match="limit"):
        monitor.dispatch_pending_notifications(limit=0)
    assert monitor.dispatch_pending_notifications() == 0

def test_malformed_notification_is_dead_lettered_without_blocking_valid_events(tmp_path):
    import json
    import uuid

    owner = TenantContext("tenant-outbox-poison", "alice")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-poison-pill.sqlite3",
        Sessions(),
        lambda _session, _context: None,
        on_result=lambda _event: None,
    )
    now = datetime.now(timezone.utc)
    current_m5 = monitor.expected_last_closed_candle("M5", now)
    connection = _id("d")
    malformed_id = str(uuid.uuid4())
    valid_id = str(uuid.uuid4())
    with monitor._connect() as db:
        db.execute(
            """
            INSERT INTO tenant_connection_notification_outbox (
                event_id, tenant_id, subject_id, connection_id, symbol,
                timeframe, candle_at, result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                malformed_id, owner.tenant_id, owner.subject_id, connection,
                "EURUSD", "M5", current_m5.isoformat(), "{not-json",
                now.timestamp(),
            ),
        )
        db.execute(
            """
            INSERT INTO tenant_connection_notification_outbox (
                event_id, tenant_id, subject_id, connection_id, symbol,
                timeframe, candle_at, result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                valid_id, owner.tenant_id, owner.subject_id, connection,
                "GBPUSD", "M5", current_m5.isoformat(),
                json.dumps({"result": {"signal": "VENDA", "status": "ANALYZED"}}),
                now.timestamp() + 1,
            ),
        )

    delivered = []
    monitor.on_result = delivered.append
    assert monitor.dispatch_pending_notifications(limit=10) == 1
    assert len(delivered) == 1
    assert delivered[0]["symbol"] == "GBPUSD"
    assert delivered[0]["result"]["signal"] == "VENDA"
    with monitor._connect() as db:
        malformed = db.execute(
            """
            SELECT dead_at, last_error, lease_until, lease_token
            FROM tenant_connection_notification_outbox WHERE event_id=?
            """,
            (malformed_id,),
        ).fetchone()
        valid = db.execute(
            "SELECT delivered_at FROM tenant_connection_notification_outbox WHERE event_id=?",
            (valid_id,),
        ).fetchone()
    assert malformed["dead_at"] is not None
    assert malformed["last_error"] == "InvalidPayload"
    assert malformed["lease_until"] is None
    assert malformed["lease_token"] is None
    assert valid["delivered_at"] is not None


def test_notification_expiry_is_scoped_to_its_own_timeframe(tmp_path):
    import json
    import uuid

    owner = TenantContext("tenant-timeframe-notifications", "alice")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "notification-timeframe-isolation.sqlite3",
        Sessions(),
        lambda _session, _context: None,
        on_result=lambda _event: None,
    )
    now = datetime.now(timezone.utc)
    expired_m1 = monitor.expected_last_closed_candle("M1", now) - timedelta(minutes=1)
    current_m5 = monitor.expected_last_closed_candle("M5", now)
    connection = _id("d")
    with monitor._connect() as db:
        for timeframe, candle_at in (("M1", expired_m1), ("M5", current_m5)):
            db.execute(
                """
                INSERT INTO tenant_connection_notification_outbox (
                    event_id, tenant_id, subject_id, connection_id, symbol,
                    timeframe, candle_at, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), owner.tenant_id, owner.subject_id,
                    connection, "EURUSD", timeframe, candle_at.isoformat(),
                    json.dumps({
                        "result": {"signal": "COMPRA", "status": "ANALYZED"},
                        "provider_id": "test_provider",
                        "source": "test",
                    }),
                    now.timestamp(),
                ),
            )

    delivered = []
    monitor.on_result = delivered.append
    assert monitor.dispatch_pending_notifications() == 2
    by_timeframe = {event["timeframe"]: event["result"] for event in delivered}
    assert by_timeframe["M1"]["signal"] is None
    assert by_timeframe["M1"]["original_signal"] == "COMPRA"
    assert by_timeframe["M1"]["status"] == "SIGNAL_EXPIRED"
    assert by_timeframe["M5"]["signal"] == "COMPRA"
    assert by_timeframe["M5"]["status"] == "ANALYZED"




@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), float("-inf"), 10**1000, "2"])
def test_monitor_rejects_invalid_poll_intervals(tmp_path, bad):
    with pytest.raises(ValueError):
        TenantConnectionTimeframeMonitor(
            tmp_path / "bad-poll.sqlite3", Sessions(),
            lambda _session, _context: Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR"),
            poll_interval_seconds=bad,
        )


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), float("-inf"), 10**1000, "0"])
def test_monitor_rejects_invalid_close_grace_values(tmp_path, bad):
    with pytest.raises(ValueError):
        TenantConnectionTimeframeMonitor(
            tmp_path / "bad-grace.sqlite3", Sessions(),
            lambda _session, _context: Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR"),
            close_grace_seconds=bad,
        )


def test_monitor_rejects_tampered_noncanonical_tenant_context(tmp_path):
    owner = TenantContext("tenant-a", "alice")
    sessions = Sessions()
    sessions.add(owner, _id("a"), "broker_a")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "bad-context.sqlite3", sessions,
        lambda _session, _context: Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR"),
    )
    object.__setattr__(owner, "subject_id", "alice" + chr(10))
    with pytest.raises(PermissionError, match="canonical trusted tenant context"):
        monitor.subscriptions(owner)


def test_live_stream_ignores_non_datetime_provider_timestamps(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-a", "alice")
    now = datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)

    class Adapter:
        account_id = "account-1"
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback

    adapter = Adapter()
    session = Session("provider", "provider:account-1", adapter)
    class Registry:
        def get(self, context, *, connection_id):
            return session

    analyzer = Analyzer("2026-11-27T12:00:00+00:00", "AGUARDAR")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "bad-stream-time.sqlite3", Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("a"), "EURUSD", "M5")
    adapter.callback({
        "account_id": "account-1", "symbol": "EURUSD", "timeframe": "M5",
        "closed": True, "candle": SimpleNamespace(timestamp="not-a-datetime", is_valid=lambda: True),
    })
    assert monitor.run_once(now=now) == []
    assert analyzer.calls == 0


@pytest.mark.parametrize(
    ("timeframe", "close_at", "before", "after", "expected_before", "expected_after"),
    [
        ("M1", "2026-11-27T12:01:00+00:00", "2026-11-27T12:01:02+00:00", "2026-11-27T12:01:03+00:00", "2026-11-27T11:59:00+00:00", "2026-11-27T12:00:00+00:00"),
        ("M5", "2026-11-27T12:05:00+00:00", "2026-11-27T12:05:02+00:00", "2026-11-27T12:05:03+00:00", "2026-11-27T11:55:00+00:00", "2026-11-27T12:00:00+00:00"),
    ],
)
def test_timeframe_close_grace_never_accepts_candle_early(
    tmp_path, timeframe, close_at, before, after, expected_before, expected_after
):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"close-grace-{timeframe}.sqlite3",
        Sessions(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
        close_grace_seconds=3,
    )
    assert monitor.expected_last_closed_candle(
        timeframe, datetime.fromisoformat(before)
    ).isoformat() == expected_before
    assert monitor.expected_last_closed_candle(
        timeframe, datetime.fromisoformat(after)
    ).isoformat() == expected_after


@pytest.mark.parametrize("invalid_now", ["2026-11-27T12:00:00+00:00", None])
def test_expected_last_closed_candle_rejects_non_datetime_now(tmp_path, invalid_now):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "invalid-now.sqlite3", Sessions(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
    )
    with pytest.raises(ValueError, match="datetime com fuso"):
        monitor.expected_last_closed_candle("M1", invalid_now)


def test_expected_last_closed_candle_rejects_naive_datetime(tmp_path):
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "naive-now.sqlite3", Sessions(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
    )
    with pytest.raises(ValueError, match="datetime com fuso"):
        monitor.expected_last_closed_candle("M1", datetime(2026, 11, 27, 12, 1))


@pytest.mark.parametrize("malformation", ["invalid_timezone", "validity_exception", "timestamp_conversion_overflow"])
def test_live_stream_discards_malformed_candle_without_breaking_worker(
    tmp_path, malformation
):
    from datetime import tzinfo
    from types import SimpleNamespace

    owner = TenantContext("tenant-malformed-live", "alice")
    expected = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

    class InvalidTimezone(tzinfo):
        def utcoffset(self, dt):
            return None

    class OverflowingTimezone(tzinfo):
        def utcoffset(self, dt):
            return timedelta(hours=1)

    class StreamAdapter:
        account_id = 987
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.callback = None

    adapter = StreamAdapter()
    session = Session("ctrader_open_api", "ctrader:987", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected.isoformat(), "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"malformed-live-{malformation}.sqlite3",
        Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, _id("d"), "EURUSD", "M5")

    if malformation == "invalid_timezone":
        candle = SimpleNamespace(
            timestamp=datetime(2026, 11, 27, 12, 0, tzinfo=InvalidTimezone()),
            is_valid=lambda: True,
        )
    elif malformation == "timestamp_conversion_overflow":
        candle = SimpleNamespace(
            timestamp=datetime.min.replace(tzinfo=OverflowingTimezone()),
            is_valid=lambda: True,
        )
    else:
        def broken_validation():
            raise RuntimeError("provider candle validation failed")
        candle = SimpleNamespace(timestamp=expected, is_valid=broken_validation)

    adapter.callback({
        "account_id": 987,
        "symbol": "EURUSD",
        "timeframe": "M5",
        "candle": candle,
        "closed": True,
    })

    assert monitor.run_once(now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)) == []
    assert analyzer.calls == 0
    assert monitor.subscriptions(owner)[0]["last_status"] == "WAITING_FOR_LIVE_CLOSED_CANDLE"


def test_expected_closed_candle_normalizes_non_utc_clock_to_utc(tmp_path):
    from datetime import timedelta

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "non-utc-close.sqlite3", Sessions(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
        close_grace_seconds=3,
    )
    local_now = datetime(
        2026, 11, 27, 9, 6, 3,
        tzinfo=timezone(timedelta(hours=-3)),
    )
    assert monitor.expected_last_closed_candle(
        "M5", local_now
    ) == datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def test_future_live_candle_cannot_poison_stream_cache(tmp_path):
    from types import SimpleNamespace

    owner = TenantContext("tenant-future-live", "alice")
    now = datetime.now(timezone.utc)
    adapter_expected = datetime(2099, 1, 1, tzinfo=timezone.utc)

    class StreamAdapter:
        account_id = 654
        def subscribe_live_candles(self, symbol, timeframe, callback):
            self.callback = callback
        def unsubscribe_live_candles(self, symbol, timeframe):
            self.callback = None

    adapter = StreamAdapter()
    session = Session("ctrader_open_api", "ctrader:654", adapter)

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "future-live-cache.sqlite3",
        Registry(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
    )
    monitor.subscribe(owner, _id("f"), "EURUSD", "M5")

    def candle(at):
        return SimpleNamespace(timestamp=at, is_valid=lambda: True)

    event = {
        "account_id": 654, "symbol": "EURUSD", "timeframe": "M5",
        "closed": True,
    }
    adapter.callback({**event, "candle": candle(adapter_expected)})
    key = ("tenant-future-live", "alice", _id("f"), "EURUSD", "5m")
    assert key not in monitor._live_candles

    valid_at = monitor.expected_last_closed_candle("M5", now)
    adapter.callback({**event, "candle": candle(valid_at)})
    assert monitor._live_candles[key].timestamp == valid_at


def test_monitor_public_clock_inputs_reject_timezone_without_utc_offset(tmp_path):
    from datetime import tzinfo

    class MissingOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    invalid_now = datetime(2026, 11, 27, 12, 6, tzinfo=MissingOffset())
    owner = TenantContext("tenant-clock-offset", "alice")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / "invalid-offset.sqlite3", Sessions(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
    )

    with pytest.raises(ValueError, match="fuso horário válido"):
        monitor.run_once(now=invalid_now)
    with pytest.raises(ValueError, match="fuso horário válido"):
        monitor.latest_results(owner, now=invalid_now)


@pytest.mark.parametrize(
    ("timeframe", "expected_at"),
    [
        ("D1", datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc)),
        ("W1", datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)),
    ],
)
def test_daily_and_weekly_signals_wait_for_provider_session_calendar(
    tmp_path, timeframe, expected_at
):
    owner = TenantContext("tenant-session-calendar", "alice")
    connection = _id("b")
    session = Session("broker_without_calendar", "broker:no-calendar")
    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected_at.isoformat(), "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"session-calendar-{timeframe}.sqlite3",
        Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, connection, "EURUSD", timeframe)

    results = monitor.run_once(
        now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    )

    assert results == []
    assert analyzer.calls == 0
    subscription = monitor.subscriptions(owner)[0]
    assert subscription["last_status"] == "WAITING_FOR_SESSION_CALENDAR"
    assert subscription["expected_last_closed_candle_at"] is None
    assert subscription["data_freshness_state"] == "SESSION_CALENDAR_UNAVAILABLE"
    assert subscription["live_stream_status"] == "SESSION_CALENDAR_UNAVAILABLE"
    assert monitor.latest_results(owner, connection)[0:1] == []


@pytest.mark.parametrize(
    ("timeframe", "expected_at"),
    [
        ("D1", datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc)),
        ("W1", datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)),
    ],
)
def test_daily_and_weekly_signals_use_provider_session_boundary_for_expiry(
    tmp_path, timeframe, expected_at
):
    owner = TenantContext("tenant-session-calendar-valid", "alice")
    connection = _id("c")

    class SessionCalendarAdapter:
        def expected_last_closed_candle(self, requested_timeframe, symbol, now, *, close_grace_seconds):
            assert requested_timeframe == {"D1": "1d", "W1": "1w"}[timeframe]
            assert symbol == "EURUSD"
            assert now.tzinfo is timezone.utc
            assert close_grace_seconds == 3.0
            return expected_at

    session = Session("broker_with_calendar", "broker:session-calendar", SessionCalendarAdapter())
    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner else None

    analyzer = Analyzer(expected_at.isoformat(), "COMPRA")
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"session-calendar-valid-{timeframe}.sqlite3",
        Registry(),
        lambda _session, _context: analyzer,
    )
    monitor.subscribe(owner, connection, "EURUSD", timeframe)

    results = monitor.run_once(
        now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc)
    )
    assert len(results) == 1
    assert results[0]["candle_at"] == expected_at.isoformat()
    current = monitor.latest_results(
        owner, connection,
        now=datetime(2026, 11, 27, 12, 6, tzinfo=timezone.utc),
    )
    assert current[0]["signal_valid"] is True
    assert "signal_valid_until" not in current[0]
    assert current[0]["result"]["signal"] == "COMPRA"


@pytest.mark.parametrize("timeframe", ["D1", "W1"])
def test_delayed_daily_weekly_notification_fails_closed_without_session_calendar(
    tmp_path, timeframe
):
    owner = TenantContext("tenant-delayed-session", "alice")
    connection = _id("e")
    session = Session("broker_without_calendar", "broker:no-calendar")

    class Registry:
        def get(self, context, *, connection_id):
            return session if context == owner and connection_id == connection else None

    delivered = []
    monitor = TenantConnectionTimeframeMonitor(
        tmp_path / f"delayed-session-{timeframe}.sqlite3",
        Registry(),
        lambda _session, _context: Analyzer(None, "AGUARDAR"),
        on_result=delivered.append,
    )
    event_id = str(uuid.uuid4())
    candle_at = datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc)
    payload = {
        "provider_id": "broker_without_calendar",
        "source": "broker:no-calendar",
        "result": {"signal": "COMPRA", "score": 82},
    }
    with monitor._connect() as db:
        db.execute(
            """
            INSERT INTO tenant_connection_notification_outbox (
                event_id, tenant_id, subject_id, connection_id, symbol,
                timeframe, candle_at, result_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, owner.tenant_id, owner.subject_id, connection,
                "EURUSD", timeframe, candle_at.isoformat(),
                json.dumps(payload), time.time(),
            ),
        )

    assert monitor.dispatch_pending_notifications() == 1
    assert len(delivered) == 1
    result = delivered[0]["result"]
    assert result["signal"] is None
    assert result["original_signal"] == "COMPRA"
    assert result["status"] == "SESSION_CALENDAR_UNAVAILABLE"
    assert result["signal_validity"] == "SESSION_CALENDAR_UNAVAILABLE"
