from __future__ import annotations

from core.kill_switch import KillSwitch
from core.market_data_runtime_integrity import MarketDataRuntimeReport
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle

from core.market_data_runtime_state import MarketDataRuntimeState
from core.p23_market_data_integrity import MarketDataHealth
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal
from integration.market_data_execution_guard import MarketDataExecutionGuard


def _request(symbol: str = "EURUSD") -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def _state(*, health: MarketDataHealth, symbol: str = "EURUSD") -> MarketDataRuntimeState:
    state = MarketDataRuntimeState(integrity=object())
    state.report = MarketDataRuntimeReport(
        source="TEST",
        symbol=symbol,
        timeframe="5m",
        health=health,
        candle_count=100,
        gap_count=0,
        stale=False,
        message="teste",
    )
    state.snapshot = BrokerMarketDataSnapshot(
        symbol=symbol,
        timeframe="5m",
        candles=(Candle(__import__("datetime").datetime.now(__import__("datetime").timezone.utc), 1, 1, 1, 1, 1),),
        source="TEST",
        received_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    return state


def test_guard_blocks_when_no_market_snapshot_exists():
    state = MarketDataRuntimeState(integrity=object())
    guard = MarketDataExecutionGuard(state, ExecutionGateway(PaperExecutor(), KillSwitch()))
    result = guard.execute("missing-data", _request())
    assert result.status is GatewayStatus.BLOCKED


def test_guard_blocks_unhealthy_market_data_before_executor():
    state = _state(health=MarketDataHealth.STALE)
    guard = MarketDataExecutionGuard(state, ExecutionGateway(PaperExecutor(), KillSwitch()))
    result = guard.execute("stale-data", _request())
    assert result.status is GatewayStatus.BLOCKED
    assert "HEALTHY" in result.message


def test_guard_blocks_symbol_mismatch():
    state = _state(health=MarketDataHealth.HEALTHY, symbol="GBPUSD")
    guard = MarketDataExecutionGuard(state, ExecutionGateway(PaperExecutor(), KillSwitch()))
    result = guard.execute("symbol-mismatch", _request("EURUSD"))
    assert result.status is GatewayStatus.BLOCKED


def test_guard_allows_healthy_matching_data_to_reach_gateway():
    state = _state(health=MarketDataHealth.HEALTHY)
    guard = MarketDataExecutionGuard(state, ExecutionGateway(PaperExecutor(), KillSwitch()))
    result = guard.execute("healthy-data", _request())
    assert result.status is GatewayStatus.ACCEPTED
