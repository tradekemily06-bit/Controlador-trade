from datetime import datetime, timezone

import pytest

from core.decision_engine import DecisionResult, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult
from core.kill_switch import KillSwitch
from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel, SignalQuality
from data.feed import MarketDataResult
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecution
from execution.ports import ExecutionMode


class FakeGateway:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "executed"


def executable_orchestration() -> OrchestrationResult:
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=80.0,
        reason="sinal de teste",
        confirmed=True,
        symbol="EURUSD",
        timeframe="5m",
    )
    quality = SignalQuality(score=90.0, level=SignalLevel.FORTE, actionable=True, reason="teste")
    decision = DecisionResult(FinalDecision.EXECUTAR, Signal.COMPRA, "aprovado")
    snapshot = DecisionSnapshot.from_results(
        analysis=analysis,
        quality=quality,
        decision=decision,
        market_context=None,
        operational_state=None,
    )
    return OrchestrationResult(
        market_data=MarketDataResult(candles=(), source="test", received_at=datetime.now(timezone.utc)),
        analysis=analysis,
        quality=quality,
        decision=decision,
        snapshot=snapshot,
        timestamp=datetime.now(timezone.utc),
    )


def test_build_plan_only_allows_executable_decision():
    plan = ExecutionCoordinator.build_plan(
        executable_orchestration(), request_id="req-1", amount=10.0, duration_seconds=60
    )
    assert isinstance(plan, ExecutionPlan)
    assert plan.request.signal is Signal.COMPRA
    assert plan.request.mode is ExecutionMode.DEMO


def test_build_plan_rejects_non_executable_decision():
    orchestration = executable_orchestration()
    non_executable = OrchestrationResult(
        market_data=orchestration.market_data,
        analysis=orchestration.analysis,
        quality=orchestration.quality,
        decision=DecisionResult(FinalDecision.AGUARDAR, Signal.COMPRA, "aguardar"),
        snapshot=orchestration.snapshot,
        timestamp=orchestration.timestamp,
    )
    with pytest.raises(ValueError, match="EXECUTAR"):
        ExecutionCoordinator.build_plan(
            non_executable, request_id="req-2", amount=10.0, duration_seconds=60
        )


def test_coordinator_forwards_plan_to_gateway():
    fake = FakeGateway()
    coordinator = ExecutionCoordinator(fake)
    orchestration = executable_orchestration()
    plan = coordinator.build_plan(
        orchestration, request_id="req-3", amount=10.0, duration_seconds=60
    )
    result = coordinator.execute_plan(
        plan, orchestration=orchestration, entry_conditions=("teste",)
    )
    assert result == "executed"
    assert fake.calls[0][0][0] == "req-3"
    assert fake.calls[0][1]["snapshot"] is orchestration.snapshot


def test_coordinator_integrates_with_demo_gateway():
    gateway = ExecutionGateway(PaperExecution(), KillSwitch())
    coordinator = ExecutionCoordinator(gateway)
    orchestration = executable_orchestration()
    plan = coordinator.build_plan(
        orchestration, request_id="req-4", amount=10.0, duration_seconds=60
    )
    result = coordinator.execute_plan(plan, orchestration=orchestration)
    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None
