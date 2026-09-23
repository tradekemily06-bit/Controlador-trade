import time
from datetime import datetime, timezone

from core.market_data_runtime_state import MarketDataRuntimeState
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle
from integration.persistent_market_data_runtime import (
    MarketDataRuntimeConfig,
    PersistentMarketDataRuntime,
)


class FakeBoundary:
    def fetch(self, request):
        now = datetime.now(timezone.utc)
        candle = Candle(
            timestamp=now,
            open=1.0,
            high=1.1,
            low=0.9,
            close=1.05,
            volume=10.0,
        )
        return BrokerMarketDataSnapshot(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles=(candle,),
            source="FAKE",
            received_at=now,
        )


def test_persistent_runtime_updates_shared_state():
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        FakeBoundary(),
        state,
        MarketDataRuntimeConfig(poll_seconds=0.01),
    )
    runtime.start()
    try:
        deadline = time.monotonic() + 1.0
        while runtime.status()["last_success"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.status()["runtime"] == "RUNNING"
        assert runtime.status()["last_success"] is not None
        assert state.status()["source"] == "FAKE"
    finally:
        runtime.stop()


def test_runtime_failure_does_not_grant_analysis_safety():
    class BrokenBoundary:
        def fetch(self, request):
            raise RuntimeError("broker offline")

    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        BrokenBoundary(),
        state,
        MarketDataRuntimeConfig(poll_seconds=0.01),
    )
    runtime.start()
    try:
        deadline = time.monotonic() + 1.0
        while runtime.status()["last_error"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.status()["last_error"] == "broker offline"
        assert state.status()["safe_for_analysis"] is False
    finally:
        runtime.stop()
