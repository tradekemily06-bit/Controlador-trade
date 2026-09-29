from __future__ import annotations

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from integration.persistent_market_data_runtime import MarketDataRuntimeConfig, PersistentMarketDataRuntime


class _Boundary:
    source = "test"

    def fetch(self, request):
        raise AssertionError("fetch não deve ser chamado neste teste")


def test_runtime_resolves_dynamic_symbol_when_no_fixed_symbol() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
        symbol_selector=lambda: "BTCUSD",
    )

    assert runtime._resolve_symbol() == "BTCUSD"
    assert runtime.status()["symbol"] is None


def test_runtime_fails_closed_when_dynamic_selector_returns_no_symbol() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
        symbol_selector=lambda: None,
    )

    assert runtime._resolve_symbol() is None


def test_runtime_can_configure_provider_neutral_candidate_analysis_before_start() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
    )
    runtime.configure_candidate_analysis(
        candidate_selector=lambda: ("EURUSD", "GBPUSD"),
        candidate_analyzer=lambda snapshot: snapshot,
    )
    status = runtime.status()
    assert status["candidate_sweep"]["enabled"] is True
    assert status["candidate_sweep"]["candidate_count"] == 0


def test_candidate_handler_failure_does_not_deadlock_runtime_status() -> None:
    import threading
    import time
    from datetime import datetime, timedelta, timezone

    from core.p122_broker_market_data import BrokerMarketDataBoundary
    from data.models import Candle

    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())

    class Provider:
        def fetch_market_data(self, request):
            now = datetime.now(timezone.utc)
            candles = tuple(
                Candle(
                    timestamp=now - timedelta(minutes=5 * (29 - index) + 1),
                    open=1.0,
                    high=1.1,
                    low=0.9,
                    close=1.05,
                    volume=1.0,
                )
                for index in range(30)
            )
            return candles

    callback_failed = threading.Event()

    def handler(snapshot, result):
        callback_failed.set()
        raise RuntimeError("callback failure")

    runtime = PersistentMarketDataRuntime(
        BrokerMarketDataBoundary(Provider(), "test"),
        state,
        MarketDataRuntimeConfig(symbol="EURUSD", timeframe="5m", limit=30, poll_seconds=0.01),
        candidate_selector=lambda: ("EURUSD",),
        candidate_analyzer=lambda snapshot: type(
            "Result",
            (),
            {"signal": "COMPRA", "confirmed": True, "score": 80.0},
        )(),
        selected_result_handler=handler,
    )
    runtime.start()
    assert callback_failed.wait(1.0)
    started = time.monotonic()
    status = runtime.status()
    runtime.stop()
    assert time.monotonic() - started < 0.5
    assert "callback failure" in str(status["last_error"])
