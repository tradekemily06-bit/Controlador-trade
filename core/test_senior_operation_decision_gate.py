from core.decision_engine import DecisionEngine, FinalDecision
from core.models import AnalysisResult, Signal
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_operation_assessment import SeniorOperationAssessment, SeniorOperationDisposition
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment


def _risk():
    return SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(), material_risks=(), unknowns=(), questions=(),
        reassessment_triggers=(), execution_authorized=False,
    )


def _context(disposition):
    assessment = SeniorOperationAssessment(
        disposition=disposition,
        quality_level="SÊNIOR" if disposition is SeniorOperationDisposition.SUITABLE else "REAVALIAR",
        reasons=("test",), strengths=(), weaknesses=(), invalidators=(),
        evidence_for=("evidence",), evidence_against=(), independent_confluences=2,
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="gate-test", whole_graph=None, temporal_context=None,
        market_reading=None, senior_assessment=None, risk_assessment=_risk(),
        validated_knowledge_ids=(), unresolved_questions=(),
        quality=SeniorContextQuality.COMPLETE, execution_authorized=False,
        operation_assessment=assessment,
    )


def _evaluate(context):
    analysis = AnalysisResult(signal=Signal.COMPRA, score=90, reason="candidate", confirmed=True, symbol="EURUSD", timeframe="5m")
    market = MarketContextResult(MarketContext.FAVORAVEL, 90, "favoravel", MarketDirection.ALTA)
    state = OperationalState(realized_pnl=0, trades_today=0, consecutive_losses=0)
    return DecisionEngine(RiskManager()).evaluate(
        analysis=analysis, market_context=market, operational_state=state, senior_context=context,
    )


def test_suitable_senior_operation_can_reach_execution_gate():
    result = _evaluate(_context(SeniorOperationDisposition.SUITABLE))
    assert result.decision == FinalDecision.EXECUTAR


def test_waiting_senior_operation_cannot_reach_execution_gate():
    result = _evaluate(_context(SeniorOperationDisposition.WAIT))
    assert result.decision == FinalDecision.AGUARDAR
    assert "Avaliação profissional" in result.reason


def test_reassessment_senior_operation_cannot_reach_execution_gate():
    result = _evaluate(_context(SeniorOperationDisposition.REASSESS))
    assert result.decision == FinalDecision.AGUARDAR
