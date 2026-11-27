from datetime import datetime, timezone
import threading

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
