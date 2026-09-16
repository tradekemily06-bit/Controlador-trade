from __future__ import annotations

from core.kill_switch import KillSwitch
from core.market_data_runtime_integrity import MarketDataRuntimeReport
from core.market_data_runtime_state import MarketDataRuntimeState
from core.p23_market_data_integrity import MarketDataHealth
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal
from integration.market_data_execution_guard import MarketDataExecutionGuard


FINGERPRINT = "a" * 64


def _request(symbol: str = "EURUSD", *, fingerprint: str | None = FINGERPRINT) -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        market_data_fingerprint=fingerprint,
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
        fingerprint=FINGERPRINT if health is MarketDataHealth.HEALTHY else None,
    )
    return state


def _gateway(executor: PaperExecutor) -> ExecutionGateway:
    return ExecutionGateway(
        executor,
        KillSwitch(),
        market_data_fingerprint_provider=lambda: FINGERPRINT,
    )


def test_guard_blocks_when_no_market_snapshot_exists():
    state = MarketDataRuntimeState(integrity=object())
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("missing-data", _request())
    assert result.status is GatewayStatus.BLOCKED


def test_guard_blocks_unhealthy_market_data_before_executor():
    state = _state(health=MarketDataHealth.STALE)
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("stale-data", _request())
    assert result.status is GatewayStatus.BLOCKED
    assert "HEALTHY" in result.message


def test_guard_blocks_symbol_mismatch():
    state = _state(health=MarketDataHealth.HEALTHY, symbol="GBPUSD")
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("symbol-mismatch", _request("EURUSD"))
    assert result.status is GatewayStatus.BLOCKED


def test_guard_blocks_when_request_market_identity_is_missing():
    state = _state(health=MarketDataHealth.HEALTHY)
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("missing-market-identity", _request(fingerprint=None))
    assert result.status is GatewayStatus.BLOCKED
    assert "identidade de mercado" in result.message


def test_guard_blocks_when_request_market_identity_mismatches():
    state = _state(health=MarketDataHealth.HEALTHY)
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("mismatched-market-identity", _request(fingerprint="b" * 64))
    assert result.status is GatewayStatus.BLOCKED
    assert "identidade de mercado" in result.message


def test_guard_blocks_when_healthy_report_has_no_market_identity():
    state = _state(health=MarketDataHealth.HEALTHY)
    state.report = MarketDataRuntimeReport(
        source="TEST",
        symbol="EURUSD",
        timeframe="5m",
        health=MarketDataHealth.HEALTHY,
        candle_count=100,
        gap_count=0,
        stale=False,
        message="teste",
        fingerprint=None,
    )
    guard = MarketDataExecutionGuard(state, _gateway(PaperExecutor()))
    result = guard.execute("missing-report-identity", _request())
    assert result.status is GatewayStatus.BLOCKED


def test_guard_allows_healthy_matching_data_to_reach_gateway():
    state = _state(health=MarketDataHealth.HEALTHY)
    executor = PaperExecutor()
    guard = MarketDataExecutionGuard(state, _gateway(executor))
    result = guard.execute("healthy-data", _request())
    assert result.status is GatewayStatus.ACCEPTED
    assert executor.executions()
