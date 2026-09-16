from datetime import datetime, timedelta, timezone

from core.decision_freshness import DecisionFreshnessPolicy
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def request():
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def make_gateway(executor):
    return ExecutionGateway(
        executor,
        KillSwitch(),
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30),
        decision_clock=lambda: NOW,
    )


def test_gateway_blocks_expired_decision_before_executor():
    executor = PaperExecutor()
    gateway = make_gateway(executor)

    result = gateway.execute(
        "stale-1",
        request(),
        timestamp=NOW - timedelta(seconds=31),
    )

    assert result.status is GatewayStatus.BLOCKED
    assert "expirada" in result.message
    assert executor.executions() == ()


def test_gateway_blocks_future_decision_before_executor():
    executor = PaperExecutor()
    gateway = make_gateway(executor)

    result = gateway.execute(
        "future-1",
        request(),
        timestamp=NOW + timedelta(seconds=3),
    )

    assert result.status is GatewayStatus.BLOCKED
    assert "futuro" in result.message
    assert executor.executions() == ()


def test_gateway_accepts_fresh_decision():
    executor = PaperExecutor()
    gateway = make_gateway(executor)

    result = gateway.execute(
        "fresh-1",
        request(),
        timestamp=NOW - timedelta(seconds=10),
    )

    assert result.status is GatewayStatus.ACCEPTED
    assert len(executor.executions()) == 1
