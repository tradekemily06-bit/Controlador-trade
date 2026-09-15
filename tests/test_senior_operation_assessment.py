from core.integrated_market_reading import IntegratedMarketReading, MarketObservation, ReadingStatus
from core.senior_market_reasoning import ProfessionalQuestion, ReasoningPosture, SeniorMarketAssessment
from core.senior_operation_assessment import SeniorOperationAssessor, SeniorOperationDisposition
from core.whole_graph_observation import WholeGraphObservationBoundary, WholeGraphStatus


def make_graph(partial=False):
    b = WholeGraphObservationBoundary()
    if partial:
        return b.audit(context_id="t", available_nodes=("a", "b"), observed_nodes=("a",), gaps={"b": "missing"})
    return b.audit(context_id="t", available_nodes=("a", "b"), observed_nodes=("a", "b"))


def make_reading(conflict=False, false_breakout=False):
    obs = (
        MarketObservation("a", "candle", "body", "BUY", 0.8, "candle"),
        MarketObservation("b", "structure", "trend", "SELL" if conflict else "BUY", 0.8, "structure"),
    )
    return IntegratedMarketReading(
        ReadingStatus.CONFLICTING if conflict else ReadingStatus.SUPPORTED,
        obs, ("a",), ("b",) if conflict else (), ("conflict",) if conflict else (),
        false_breakout, (),
    )


def make_reasoning(posture=ReasoningPosture.ACT):
    return SeniorMarketAssessment(posture, "context", ("obs",), (), (),
        (ProfessionalQuestion("context", "what changed?"),), ("a",), (), ("uncertain",), False)


def test_suitable():
    result = SeniorOperationAssessor().assess(graph=make_graph(), reading=make_reading(), reasoning=make_reasoning())
    assert result.disposition is SeniorOperationDisposition.SUITABLE
    assert result.execution_authorized is False


def test_conflict_reassesses():
    result = SeniorOperationAssessor().assess(graph=make_graph(), reading=make_reading(conflict=True), reasoning=make_reasoning())
    assert result.disposition is SeniorOperationDisposition.REASSESS
    assert result.evidence_against


def test_false_breakout_reassesses():
    result = SeniorOperationAssessor().assess(graph=make_graph(), reading=make_reading(false_breakout=True), reasoning=make_reasoning(ReasoningPosture.REASSESS))
    assert result.disposition is SeniorOperationDisposition.REASSESS
    assert result.invalidators


def test_partial_context_reassesses():
    result = SeniorOperationAssessor().assess(graph=make_graph(partial=True), reading=make_reading(), reasoning=make_reasoning())
    assert result.disposition is SeniorOperationDisposition.REASSESS
