from datetime import datetime, timezone

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest
from execution.paper import PaperExecutor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def request(signal=Signal.COMPRA, symbol="EURUSD"):
    return ExecutionRequest(
        symbol=symbol,
        signal=signal,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def snapshot(signal="COMPRA", symbol="EURUSD", decision="EXECUTAR", actionable=True, created_at=NOW):
    return DecisionSnapshot(
        signal=signal,
        analysis_score=90.0,
        confirmed=True,
        quality_score=90.0,
        quality_level="FORTE",
        actionable=actionable,
        decision=decision,
        decision_reason="decisão validada",
        market_context="FAVORAVEL",
        market_direction="ALTA",
        market_score=90.0,
        operational_state_available=True,
        trades_today=0,
        consecutive_losses=0,
        symbol=symbol,
        timeframe="5m",
        created_at=created_at,
    )


def operational_gateway(executor=None):
    return ExecutionGateway(
        executor or PaperExecutor(),
        KillSwitch(),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30),
        decision_clock=lambda: NOW,
    )


def test_operational_gateway_requires_snapshot():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute("snapshot-required", request(), timestamp=NOW)
    assert result.status is GatewayStatus.BLOCKED
    assert "snapshot" in result.message
    assert executor.executions() == ()


def test_operational_gateway_requires_authoritative_snapshot_timestamp():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute(
        "snapshot-created-at-required",
        request(),
        snapshot=snapshot(created_at=None),
        timestamp=NOW,
    )
    assert result.status is GatewayStatus.BLOCKED
    assert "created_at" in result.message
    assert executor.executions() == ()


def test_operational_gateway_blocks_symbol_mismatch():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute(
        "snapshot-symbol",
        request(symbol="GBPUSD"),
        snapshot=snapshot(symbol="EURUSD"),
        timestamp=NOW,
    )
    assert result.status is GatewayStatus.BLOCKED
    assert "símbolo" in result.message
    assert executor.executions() == ()


def test_operational_gateway_blocks_signal_mismatch():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute(
        "snapshot-signal",
        request(signal=Signal.VENDA),
        snapshot=snapshot(signal="COMPRA"),
        timestamp=NOW,
    )
    assert result.status is GatewayStatus.BLOCKED
    assert "sinal" in result.message
    assert executor.executions() == ()


def test_operational_gateway_blocks_non_executable_snapshot():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute(
        "snapshot-decision",
        request(),
        snapshot=snapshot(decision="AGUARDAR", actionable=False),
        timestamp=NOW,
    )
    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_operational_gateway_accepts_matching_snapshot():
    executor = PaperExecutor()
    result = operational_gateway(executor).execute(
        "snapshot-ok",
        request(),
        snapshot=snapshot(),
        timestamp=NOW,
    )
    assert result.status is GatewayStatus.ACCEPTED
    assert len(executor.executions()) == 1
