from datetime import datetime, timezone

import pytest

from core.decision_engine import DecisionResult, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.live_orchestrator import OrchestrationResult
from core.kill_switch import KillSwitch
from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel, SignalQuality
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment
from data.feed import MarketDataResult
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode


class FakeGateway:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "executed"


def make_senior_context(quality=SeniorContextQuality.COMPLETE):
    risk = SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(),
        material_risks=(),
        unknowns=(),
        questions=(),
        reassessment_triggers=(),
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="execution-coordinator-test",
        whole_graph=None,
        temporal_context=None,
        market_reading=None,
        senior_assessment=None,
        risk_assessment=risk,
        validated_knowledge_ids=(),
        unresolved_questions=(),
        quality=quality,
        execution_authorized=False,
    )


def executable_orchestration(senior_context=None) -> OrchestrationResult:
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=80.0,
        reason="sinal de teste",
        confirmed=True,
        symbol="EURUSD",
        timeframe="5m",
    )
    quality = SignalQuality(score=90.0, level=SignalLevel.FORTE, actionable=True)
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
        senior_context=senior_context if senior_context is not None else make_senior_context(),
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
        senior_context=orchestration.senior_context,
    )
    with pytest.raises(ValueError, match="EXECUTAR"):
        ExecutionCoordinator.build_plan(
            non_executable, request_id="req-2", amount=10.0, duration_seconds=60
        )


def test_coordinator_forwards_plan_only_after_senior_admission():
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
    assert fake.calls[0][1]["entry_conditions"] == ("teste",)


def test_coordinator_blocks_missing_senior_context():
    fake = FakeGateway()
    coordinator = ExecutionCoordinator(fake)
    orchestration = executable_orchestration(senior_context=None)
    orchestration = OrchestrationResult(
        market_data=orchestration.market_data,
        analysis=orchestration.analysis,
        quality=orchestration.quality,
        decision=orchestration.decision,
        snapshot=orchestration.snapshot,
        timestamp=orchestration.timestamp,
        senior_context=None,
    )
    with pytest.raises(ValueError, match="contexto sênior obrigatório"):
        coordinator.build_plan(orchestration, request_id="req-missing", amount=10.0, duration_seconds=60)
    assert fake.calls == []


def test_coordinator_integrates_with_demo_gateway():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())
    coordinator = ExecutionCoordinator(gateway)
    orchestration = executable_orchestration()
    plan = coordinator.build_plan(
        orchestration, request_id="req-4", amount=10.0, duration_seconds=60
    )
    result = coordinator.execute_plan(plan, orchestration=orchestration)
    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None


def test_build_plan_can_represent_explicit_real_selection():
    plan = ExecutionCoordinator.build_plan(
        executable_orchestration(),
        request_id="real-plan-1",
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
    )
    assert plan.request.mode is ExecutionMode.REAL
