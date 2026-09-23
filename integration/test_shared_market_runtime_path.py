from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.operational_runtime import build_operational_runtime
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle
from execution.ports import ExecutionResult
from integration.ecosystem_service import EcosystemService


class GuardedExecutor:
    def __init__(self) -> None:
        self.requests = []

    def is_available(self):
        return True

    def execute(self, request):
        self.requests.append(request)
        return ExecutionResult(True, "DEMO accepted", "runtime-demo-1")

    def read_operational_state(self):
        from core.operational_state import OperationalState
        return OperationalState(realized_pnl=0.0, trades_today=0, consecutive_losses=0)


def healthy_snapshot(symbol: str = "EURUSD", timeframe: str = "5m") -> BrokerMarketDataSnapshot:
    now = datetime.now(timezone.utc)
    candles = tuple(
        Candle(
            timestamp=now - timedelta(minutes=5 * (29 - index) + 1),
            open=1.1000 + index * 0.0001,
            high=1.1005 + index * 0.0001,
            low=1.0995 + index * 0.0001,
            close=1.1002 + index * 0.0001,
            volume=100 + index,
        )
        for index in range(30)
    )
    return BrokerMarketDataSnapshot(symbol, timeframe, candles, "TEST_RUNTIME", now)


def test_market_analysis_consumes_only_shared_runtime_snapshot(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path, executor=GuardedExecutor())
    runtime.market_data.update(healthy_snapshot(), now=datetime.now(timezone.utc))
    
    class FailingProvider:
        def fetch_market_data(self, request):
            raise AssertionError("second broker-data path must never be used")

    service = EcosystemService(
        operational_runtime=runtime,
        market_data_provider=FailingProvider(),
        market_data_source="TEST_SECOND_PATH",
    )

    decision = service.analyze_market(symbol="EURUSD", timeframe="5m", limit=120)

    assert decision.symbol == "EURUSD"
    assert decision.timeframe == "5m"
    assert runtime.market_data.validated_snapshot(symbol="EURUSD", timeframe="5m") is not None


def test_market_data_refresh_failure_invalidates_execution_path(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path, executor=GuardedExecutor())
    runtime.market_data.update(healthy_snapshot(), now=datetime.now(timezone.utc))
    assert runtime.market_data.status()["safe_for_analysis"] is True

    runtime.market_data.invalidate(
        source="TEST_RUNTIME",
        symbol="EURUSD",
        timeframe="5m",
        message="provider offline",
    )

    assert runtime.market_data.status()["safe_for_analysis"] is False
    assert runtime.market_data.validated_snapshot(symbol="EURUSD", timeframe="5m") is None
