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
from core.senior_operation_assessment import SeniorOperationAssessment, SeniorOperationDisposition
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment
from data.feed import MarketDataResult
from data.models import Candle
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode


class FakeGateway:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "executed"


def make_senior_context(quality=SeniorContextQuality.COMPLETE, knowledge_ids=()):
    risk = SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(),
        material_risks=(),
        unknowns=(),
        questions=(),
        reassessment_triggers=(),
        execution_authorized=False,
    )
    operation = SeniorOperationAssessment(
        disposition=SeniorOperationDisposition.SUITABLE,
        quality_level="HIGH",
        reasons=("fixture profissionalmente avaliado",),
        strengths=("evidência suficiente",),
        weaknesses=(),
        invalidators=(),
        evidence_for=("fixture",),
        evidence_against=(),
        independent_confluences=("estrutura", "confirmação"),
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="execution-coordinator-test",
        whole_graph=None,
        temporal_context=None,
        market_reading=None,
        senior_assessment=None,
        risk_assessment=risk,
        validated_knowledge_ids=knowledge_ids,
        unresolved_questions=(),
        quality=quality,
        execution_authorized=False,
        operation_assessment=operation,
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


def test_build_plan_preserves_market_data_fingerprint():
    orchestration = executable_orchestration()
    plan = ExecutionCoordinator.build_plan(
        orchestration,
        request_id="req-fingerprint",
        amount=10.0,
        duration_seconds=60,
    )
    assert plan.request.market_data_fingerprint == orchestration.market_data.fingerprint
    assert plan.decision_identity


def test_coordinator_blocks_plan_when_market_data_identity_changes():
    orchestration = executable_orchestration()
    plan = ExecutionCoordinator.build_plan(
        orchestration,
        request_id="req-fingerprint-change",
        amount=10.0,
        duration_seconds=60,
    )
    changed = executable_orchestration()
    changed = OrchestrationResult(
        market_data=MarketDataResult(
            candles=(
                Candle(
                    timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc),
                    open=1.0,
                    high=1.1,
                    low=0.9,
                    close=1.05,
                ),
            ),
            source="test",
            received_at=changed.timestamp,
        ),
        analysis=changed.analysis,
        quality=changed.quality,
        decision=changed.decision,
        snapshot=changed.snapshot,
        timestamp=changed.timestamp,
        senior_context=changed.senior_context,
    )
    gateway = FakeGateway()
    result = ExecutionCoordinator(gateway).execute_plan(plan, orchestration=changed)
    assert result.status is GatewayStatus.BLOCKED
    assert "dados de mercado" in result.message
    assert gateway.calls == []


def test_coordinator_blocks_when_decision_identity_changes():
    orchestration = executable_orchestration()
    plan = ExecutionCoordinator.build_plan(
        orchestration,
        request_id="req-decision-change",
        amount=10.0,
        duration_seconds=60,
    )
    changed_analysis = AnalysisResult(
        signal=Signal.VENDA,
        score=82.0,
        reason="sinal alterado",
        confirmed=True,
        symbol="EURUSD",
        timeframe="5m",
    )
    changed_quality = SignalQuality(score=91.0, level=SignalLevel.FORTE, actionable=True)
    changed_decision = DecisionResult(FinalDecision.EXECUTAR, Signal.VENDA, "decisão alterada")
    changed_snapshot = DecisionSnapshot.from_results(
        analysis=changed_analysis,
        quality=changed_quality,
        decision=changed_decision,
        market_context=None,
        operational_state=None,
    )
    changed = OrchestrationResult(
        market_data=orchestration.market_data,
        analysis=changed_analysis,
        quality=changed_quality,
        decision=changed_decision,
        snapshot=changed_snapshot,
        timestamp=orchestration.timestamp,
        senior_context=orchestration.senior_context,
    )
    gateway = FakeGateway()
    result = ExecutionCoordinator(gateway).execute_plan(plan, orchestration=changed)
    assert result.status is GatewayStatus.BLOCKED
    assert "decisão/orquestração mudou" in result.message
    assert gateway.calls == []


def test_coordinator_blocks_when_validated_knowledge_changes():
    original_context = make_senior_context(knowledge_ids=("knowledge-A",))
    orchestration = executable_orchestration(senior_context=original_context)
    plan = ExecutionCoordinator.build_plan(
        orchestration,
        request_id="req-knowledge-change",
        amount=10.0,
        duration_seconds=60,
    )
    changed_context = make_senior_context(knowledge_ids=("knowledge-B",))
    changed = executable_orchestration(senior_context=changed_context)
    changed = OrchestrationResult(
        market_data=orchestration.market_data,
        analysis=changed.analysis,
        quality=changed.quality,
        decision=changed.decision,
        snapshot=changed.snapshot,
        timestamp=orchestration.timestamp,
        senior_context=changed_context,
    )
    gateway = FakeGateway()
    result = ExecutionCoordinator(gateway).execute_plan(plan, orchestration=changed)
    assert result.status is GatewayStatus.BLOCKED
    assert "decisão/orquestração mudou" in result.message
    assert gateway.calls == []


def test_coordinator_blocks_when_entry_conditions_change():
    orchestration = executable_orchestration()
    plan = ExecutionCoordinator.build_plan(
        orchestration,
        request_id="req-entry-change",
        amount=10.0,
        duration_seconds=60,
        entry_conditions=("rejeicao", "confirmacao_fechamento"),
    )
    gateway = FakeGateway()
    result = ExecutionCoordinator(gateway).execute_plan(
        plan,
        orchestration=orchestration,
        entry_conditions=("rompimento",),
    )
    assert result.status is GatewayStatus.BLOCKED
    assert "condições de entrada mudaram" in result.message
    assert gateway.calls == []


def test_coordinator_integrates_with_demo_gateway():
    orchestration = executable_orchestration()
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        market_data_fingerprint_provider=lambda: orchestration.market_data.fingerprint,
    )
    coordinator = ExecutionCoordinator(gateway)
    plan = coordinator.build_plan(
        orchestration, request_id="req-4", amount=10.0, duration_seconds=60
    )
    result = coordinator.execute_plan(plan, orchestration=orchestration)
    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None
