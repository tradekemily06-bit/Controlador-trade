from core.integrated_market_reading import IntegratedMarketReading, MarketObservation, ReadingStatus
from core.senior_market_intelligence import SeniorIntelligenceAssessment, SeniorIntelligenceStatus
from core.senior_market_reasoning import ProfessionalQuestion, ReasoningPosture, SeniorMarketAssessment
from core.senior_operation_assessment import SeniorOperationAssessor, SeniorOperationDisposition
from core.whole_graph_observation import WholeGraphObservation, WholeGraphStatus


def graph(status=WholeGraphStatus.COMPLETE):
    return WholeGraphObservation(
        context_id="op-test",
        status=status,
        available_nodes=("history", "present", "structure"),
        observed_nodes=("history", "present", "structure") if status is WholeGraphStatus.COMPLETE else ("history",),
        gaps=(),
        relationships_reviewed=("structure",),
    )


def reading(*, conflicting=False, false_breakout=False):
    observations = (
        MarketObservation("candle", "candle", "body", "BUY", 0.8, "candle"),
        MarketObservation("trend", "structure", "trend", "SELL" if conflicting else "BUY", 0.8, "structure"),
    )
    return IntegratedMarketReading(
        status=ReadingStatus.CONFLICTING if conflicting else ReadingStatus.SUPPORTED,
        observations=observations,
        supporting=("candle",) if not conflicting else ("candle",),
        contradicting=("trend",) if conflicting else (),
        conflicts=("conflict",) if conflicting else (),
        possible_false_breakout=false_breakout,
        unanswered_questions=(),
    )


def reasoning(posture=ReasoningPosture.ACT):
    return SeniorMarketAssessment(
        posture=posture,
        context_statement="context",
        observations=("observation",),
        considerations=(),
        avoid_assumptions=(),
        questions=(ProfessionalQuestion("context", "what changed?"),),
        evidence_for=("candle",),
        evidence_against=(),
        uncertainty=("future is conditional",),
        execution_authorized=False,
    )


def intelligence(status=SeniorIntelligenceStatus.READY):
    return SeniorIntelligenceAssessment(
        status=status,
        context_id="op-test",
        knowledge_ids=("k1",),
        principles_checked=("evidence",),
        strengths=(),
        gaps=(),
        required_reassessment=(),
        execution_authorized=False,
    )


def test_suitable_requires_real_independent_support():
    result = SeniorOperationAssessor().assess(
        graph=graph(), reading=reading(), reasoning=reasoning(), intelligence=intelligence()
    )
    assert result.disposition is SeniorOperationDisposition.SUITABLE
    assert result.execution_authorized is False
    assert result.independent_confluences == 2


def test_conflict_requires_reassessment():
    result = SeniorOperationAssessor().assess(
        graph=graph(), reading=reading(conflicting=True), reasoning=reasoning(), intelligence=intelligence()
    )
    assert result.disposition is SeniorOperationDisposition.REASSESS
    assert result.execution_authorized is False
    assert result.evidence_against


def test_false_breakout_is_not_treated_as_good_entry():
    result = SeniorOperationAssessor().assess(
        graph=graph(), reading=reading(false_breakout=True), reasoning=reasoning(ReasoningPosture.REASSESS), intelligence=intelligence()
    )
    assert result.disposition is SeniorOperationDisposition.REASSESS
    assert result.invalidators


def test_partial_context_cannot_be_suitable():
    result = SeniorOperationAssessor().assess(
        graph=graph(WholeGraphStatus.PARTIAL), reading=reading(), reasoning=reasoning(), intelligence=intelligence()
    )
    assert result.disposition is SeniorOperationDisposition.REASSESS
