from __future__ import annotations

import pytest

from core.integrated_market_reading import (
    IntegratedMarketReading,
    MarketObservation,
    ReadingStatus,
)
from core.senior_context_cycle import SeniorContextCycleBoundary, SeniorContextQuality
from core.senior_market_reasoning import (
    ProfessionalQuestion,
    ReasoningPosture,
    SeniorMarketAssessment,
)
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment
from core.temporal_market_context import TemporalMarketContext
from core.whole_graph_observation import WholeGraphObservationBoundary, WholeGraphStatus


def _assessment(*, execution_authorized: bool = False) -> SeniorMarketAssessment:
    return SeniorMarketAssessment(
        posture=ReasoningPosture.WAIT,
        context_statement="context",
        observations=("present",),
        considerations=(),
        avoid_assumptions=(),
        questions=(ProfessionalQuestion("contexto", "What changed?"),),
        evidence_for=("candle-body",),
        evidence_against=(),
        uncertainty=("future is conditional",),
        execution_authorized=execution_authorized,
    )


def _reading(status: ReadingStatus = ReadingStatus.SUPPORTED) -> IntegratedMarketReading:
    observation = MarketObservation(
        observation_id="candle-body",
        domain="candle",
        statement="body observed",
        direction="BUY",
        strength=0.7,
        independent_key="candle_behavior",
    )
    return IntegratedMarketReading(
        status=status,
        observations=(observation,),
        supporting=("candle-body",) if status is ReadingStatus.SUPPORTED else (),
        contradicting=(),
        conflicts=(),
        possible_false_breakout=False,
        unanswered_questions=(),
    )


def _temporal() -> TemporalMarketContext:
    return TemporalMarketContext((), (), (), "context", ("future is conditional",))


def _risk(status: RiskKnowledgeStatus = RiskKnowledgeStatus.ASSESSED, *, execution_authorized: bool = False) -> SeniorRiskAssessment:
    return SeniorRiskAssessment(
        status=status,
        observations=(),
        material_risks=(),
        unknowns=(),
        questions=("What is the current risk?",),
        reassessment_triggers=("material change",),
        execution_authorized=execution_authorized,
    )


def _graph(context_id: str, *, partial: bool = False):
    return WholeGraphObservationBoundary().audit(
        context_id=context_id,
        available_nodes=("history", "present", "reading"),
        observed_nodes=("history", "present") if partial else ("history", "present", "reading"),
        gaps={"reading": "reading source incomplete"} if partial else {},
    )


def test_senior_cycle_preserves_traceability_and_never_authorizes_execution() -> None:
    graph = _graph("cycle-1")
    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-1",
        whole_graph=graph,
        temporal_context=_temporal(),
        market_reading=_reading(),
        senior_assessment=_assessment(),
        risk_assessment=_risk(),
        validated_knowledge_ids=("k-1", "k-1", "k-2"),
    )

    assert graph.status is WholeGraphStatus.COMPLETE
    assert cycle.validated_knowledge_ids == ("k-1", "k-2")
    assert cycle.unresolved_questions == ("What changed?",)
    assert cycle.quality is SeniorContextQuality.COMPLETE
    assert cycle.execution_authorized is False


def test_conflicting_reading_stays_unresolved_and_adds_investigation_question() -> None:
    graph = _graph("cycle-2")
    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-2",
        whole_graph=graph,
        temporal_context=_temporal(),
        market_reading=_reading(ReadingStatus.CONFLICTING),
        senior_assessment=_assessment(),
        risk_assessment=_risk(),
    )

    assert "What evidence is still needed to resolve the reading?" in cycle.unresolved_questions
    assert cycle.quality is SeniorContextQuality.REASSESS
    assert cycle.execution_authorized is False


def test_partial_graph_remains_explicitly_partial() -> None:
    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-partial",
        whole_graph=_graph("cycle-partial", partial=True),
        temporal_context=_temporal(),
        market_reading=_reading(),
        senior_assessment=_assessment(),
        risk_assessment=_risk(),
    )

    assert cycle.quality is SeniorContextQuality.PARTIAL
    assert cycle.whole_graph.complete is False
    assert cycle.execution_authorized is False


def test_missing_risk_knowledge_forces_reassessment() -> None:
    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-risk",
        whole_graph=_graph("cycle-risk"),
        temporal_context=_temporal(),
        market_reading=_reading(),
        senior_assessment=_assessment(),
        risk_assessment=_risk(RiskKnowledgeStatus.REASSESS),
    )

    assert cycle.quality is SeniorContextQuality.REASSESS
    assert "risk information" in cycle.unresolved_questions[-1].lower()


def test_insufficient_whole_graph_fails_closed() -> None:
    graph = WholeGraphObservationBoundary().audit(
        context_id="cycle-3",
        available_nodes=(),
        observed_nodes=(),
    )

    with pytest.raises(ValueError, match="insufficient whole-graph context"):
        SeniorContextCycleBoundary().assemble(
            cycle_id="cycle-3",
            whole_graph=graph,
            temporal_context=_temporal(),
            market_reading=_reading(),
            senior_assessment=_assessment(),
            risk_assessment=_risk(),
        )


def test_insufficient_reading_fails_closed() -> None:
    with pytest.raises(ValueError, match="insufficient market reading"):
        SeniorContextCycleBoundary().assemble(
            cycle_id="cycle-4",
            whole_graph=_graph("cycle-4"),
            temporal_context=_temporal(),
            market_reading=_reading(ReadingStatus.INSUFFICIENT),
            senior_assessment=_assessment(),
            risk_assessment=_risk(),
        )


def test_neither_reasoning_nor_risk_can_smuggle_execution_authority() -> None:
    with pytest.raises(ValueError, match="senior assessment"):
        SeniorContextCycleBoundary().assemble(
            cycle_id="cycle-5",
            whole_graph=_graph("cycle-5"),
            temporal_context=_temporal(),
            market_reading=_reading(),
            senior_assessment=_assessment(execution_authorized=True),
            risk_assessment=_risk(),
        )

    with pytest.raises(ValueError, match="risk assessment"):
        SeniorContextCycleBoundary().assemble(
            cycle_id="cycle-6",
            whole_graph=_graph("cycle-6"),
            temporal_context=_temporal(),
            market_reading=_reading(),
            senior_assessment=_assessment(),
            risk_assessment=_risk(execution_authorized=True),
        )
