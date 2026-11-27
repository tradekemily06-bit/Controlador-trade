from datetime import datetime, timezone
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
    assert len(monitor.latest_results(owner, _id("a"))) == 1
    assert len(monitor.latest_results(owner, _id("b"))) == 1
    assert monitor.latest_results(owner, _id("a"))[0]["result"]["signal"] == "COMPRA"
    assert monitor.latest_results(owner, _id("b"))[0]["result"]["signal"] == "VENDA"


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
        "account_id": 123, "symbol": "EURUSD", "timeframe": "5m",
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
    saved = monitor.latest_results(owner, _id("2"))
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
            "SELECT lease_token, delivered_at FROM tenant_connection_notification_outbox WHERE event_id=?",
            (row["event_id"],),
        ).fetchone()
        assert reclaimed["lease_token"]
        assert reclaimed["delivered_at"] is None

    release.set()
    first.join(3)
    assert not first.is_alive()
    with monitor._connect() as db:
        final = db.execute(
            "SELECT lease_token, delivered_at FROM tenant_connection_notification_outbox WHERE event_id=?",
            (row["event_id"],),
        ).fetchone()
    assert final["lease_token"] == reclaimed["lease_token"]
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
    )
    holder["monitor"] = monitor
    monitor.subscribe(owner, connection, "EURUSD", "5m")
    assert len(monitor.run_once(now=now)) == 1
    monitor.on_result = sink

    # The callback succeeds, but expires its lease before durable acknowledgement.
    assert monitor.dispatch_pending_notifications() == 0
    with monitor._connect() as db:
        row = db.execute(
            "SELECT delivered_at FROM tenant_connection_notification_outbox"
        ).fetchone()
    assert row["delivered_at"] is None

