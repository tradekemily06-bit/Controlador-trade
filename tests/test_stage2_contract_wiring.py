from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.demo_risk_state_store import DemoRiskStateStore
from core.kill_switch import KillSwitch
from core.operational_runtime import build_operational_runtime
from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_identity
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class Provider:
    def __init__(self, state: OperationalState) -> None:
        self.state = state

    def current_risk_state(self) -> OperationalState:
        return self.state


class RecordingExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        return ExecutionResult(True, "ok", external_id="TEST-1")


def snapshot_for(state: OperationalState, *, created_at: datetime | None = None) -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA",
        analysis_score=90.0,
        confirmed=True,
        quality_score=90.0,
        quality_level="FORTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="teste",
        market_context="NEUTRO",
        market_direction="ALTA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=state.trades_today,
        consecutive_losses=state.consecutive_losses,
        symbol="TEST",
        timeframe="5m",
        risk_state_identity=risk_state_identity(state),
        created_at=created_at or datetime.now(timezone.utc),
    )


def request() -> ExecutionRequest:
    from core.models import Signal

    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_operational_runtime_connects_authoritative_risk_and_global_barrier(tmp_path: Path) -> None:
    runtime = build_operational_runtime(tmp_path)

    assert isinstance(runtime.gateway._risk_state_provider, DemoRiskStateStore)
    assert runtime.gateway._operational_barrier_provider is not None
    assert isinstance(runtime.gateway._decision_freshness_policy, DecisionFreshnessPolicy)


def test_gateway_binds_snapshot_risk_identity_into_final_request() -> None:
    state = OperationalState(trades_today=1, consecutive_losses=0)
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), risk_state_provider=Provider(state))

    result = gateway.execute("req-bind", request(), snapshot=snapshot_for(state))

    assert result.status is GatewayStatus.ACCEPTED
    assert executor.requests[0].risk_state_fingerprint == risk_state_identity(state)


def test_freshness_policy_blocks_expired_snapshot_before_executor() -> None:
    state = OperationalState(trades_today=1, consecutive_losses=0)
    executor = RecordingExecutor()
    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        risk_state_provider=Provider(state),
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30.0),
    )
    stale = snapshot_for(state, created_at=datetime.now(timezone.utc) - timedelta(minutes=2))

    result = gateway.execute("req-stale", request(), snapshot=stale)

    assert result.status is GatewayStatus.BLOCKED
    assert executor.requests == []
