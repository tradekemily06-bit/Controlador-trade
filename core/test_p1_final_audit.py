from core.decision_engine import DecisionEngine, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.market_context import MarketContextEngine
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from core.signal_quality import SignalLevel, SignalQualityEvaluator
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_operation_assessment import SeniorOperationAssessment, SeniorOperationDisposition
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment


def operational_state() -> OperationalState:
    return OperationalState(
        realized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
    )


def confirmed_buy() -> AnalysisResult:
    return AnalysisResult(
        signal=Signal.COMPRA,
        score=100.0,
        reason="Sinal forte confirmado.",
        confirmed=True,
        symbol="BTCUSD",
        timeframe="5m",
    )


def favorable_up_context():
    return MarketContextEngine().evaluate(
        trend_strength=100.0,
        volatility_quality=100.0,
        liquidity_quality=100.0,
        direction=MarketDirection.ALTA,
    )


def make_senior_context():
    senior_risk = SeniorRiskAssessment(
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
        reasons=("contexto profissional explicitamente validado no teste",),
        strengths=("evidência suficiente", "sem contradição material"),
        weaknesses=(),
        invalidators=(),
        evidence_for=("sinal confirmado", "contexto favorável"),
        evidence_against=(),
        independent_confluences=("estrutura", "confirmação"),
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="p1-final-audit-senior-context",
        whole_graph=None,
        temporal_context=None,
        market_reading=None,
        senior_assessment=None,
        risk_assessment=senior_risk,
        validated_knowledge_ids=(),
        unresolved_questions=(),
        quality=SeniorContextQuality.COMPLETE,
        execution_authorized=False,
        operation_assessment=operation,
    )


def test_p1_final_audit_actionable_path_is_consistent():
    analysis = confirmed_buy()
    quality = SignalQualityEvaluator().evaluate(analysis)
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_up_context(),
        operational_state=operational_state(),
        senior_context=make_senior_context(),
    )

    assert quality.actionable is True
    assert quality.level is SignalLevel.FORTE
    assert decision.decision == FinalDecision.EXECUTAR
    assert decision.signal is Signal.COMPRA

    snapshot = DecisionSnapshot.from_results(
        analysis=analysis,
        quality=quality,
        decision=decision,
        market_context=favorable_up_context(),
        operational_state=operational_state(),
    )

    assert snapshot.decision == FinalDecision.EXECUTAR
    assert snapshot.actionable is True
    assert snapshot.market_direction == MarketDirection.ALTA.value
    assert snapshot.operational_state_available is True
    assert snapshot.trades_today == 0
    assert snapshot.consecutive_losses == 0


def test_p1_final_audit_fail_closed_without_operational_state():
    analysis = confirmed_buy()
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=favorable_up_context(),
        operational_state=None,
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "Estado operacional" in decision.reason


def test_p1_final_audit_fail_closed_without_market_context():
    analysis = confirmed_buy()
    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=None,
        operational_state=operational_state(),
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "Contexto de mercado" in decision.reason


def test_p1_final_audit_direction_mismatch_never_executes():
    analysis = confirmed_buy()
    context = MarketContextEngine().evaluate(
        trend_strength=100.0,
        volatility_quality=100.0,
        liquidity_quality=100.0,
        direction=MarketDirection.BAIXA,
    )

    decision = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=operational_state(),
    )

    assert decision.decision == FinalDecision.AGUARDAR
    assert "incompatível" in decision.reason


def test_p1_final_audit_risk_limit_blocks_execution():
    analysis = confirmed_buy()
    risk_manager = RiskManager(max_operations=1)
    state = OperationalState(
        realized_pnl=0.0,
        trades_today=1,
        consecutive_losses=0,
    )

    decision = DecisionEngine(risk_manager).evaluate(
        analysis=analysis,
        market_context=favorable_up_context(),
        operational_state=state,
    )

    assert decision.decision == FinalDecision.BLOQUEAR
    assert "Limite de operações" in decision.reason
