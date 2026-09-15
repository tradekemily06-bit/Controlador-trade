from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def _snapshot(created_at: datetime) -> DecisionSnapshot:
    return DecisionSnapshot(
        signal=Signal.COMPRA.value,
        analysis_score=95.0,
        confirmed=True,
        quality_score=95.0,
        quality_level="EXCELENTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="contexto consistente",
        market_context="ALTA",
        market_direction="ALTA",
        market_score=95.0,
        operational_state_available=True,
        trades_today=0,
        consecutive_losses=0,
        symbol="BTCUSD",
        timeframe="5m",
        created_at=created_at,
    )


def _ready_barrier():
    return SimpleNamespace(
        evaluate=lambda: SimpleNamespace(
            operationally_allowed=True,
            reason="operacional",
        )
    )


def test_operational_gateway_uses_snapshot_created_at_not_request_timestamp_for_freshness():
    now = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)
    stale = now - timedelta(seconds=31)
    executor = PaperExecutor()
    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        operational_barrier_provider=_ready_barrier,
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30.0, max_future_skew_seconds=2.0),
        decision_clock=lambda: now,
    )

    result = gateway.execute(
        "fresh-request-id",
        _request(),
        snapshot=_snapshot(stale),
        timestamp=now,
    )

    assert result.status is GatewayStatus.BLOCKED
    assert "frescor" in result.message or "expir" in result.message
    assert executor.executions() == ()


def test_operational_gateway_accepts_fresh_snapshot_with_current_request_timestamp():
    now = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(seconds=5)
    executor = PaperExecutor()
    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        operational_barrier_provider=_ready_barrier,
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30.0, max_future_skew_seconds=2.0),
        decision_clock=lambda: now,
    )

    result = gateway.execute(
        "fresh-snapshot-id",
        _request(),
        snapshot=_snapshot(fresh),
        timestamp=now,
    )

    assert result.status is GatewayStatus.ACCEPTED
    assert len(executor.executions()) == 1
