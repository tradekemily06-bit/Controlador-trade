from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.integrated_market_reading import (
    IntegratedMarketReading,
    MarketObservation,
    ReadingStatus,
)
from core.senior_context_cycle import SeniorContextCycleBoundary
from core.senior_market_reasoning import (
    ProfessionalQuestion,
    ReasoningPosture,
    SeniorMarketAssessment,
)
from core.temporal_market_context import TemporalMarketContext
from core.whole_graph_observation import WholeGraphObservationBoundary, WholeGraphStatus


def _assessment() -> SeniorMarketAssessment:
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


def test_senior_cycle_preserves_traceability_and_never_authorizes_execution() -> None:
    graph = WholeGraphObservationBoundary().audit(
        context_id="cycle-1",
        available_nodes=("history", "present", "reading", "knowledge"),
        observed_nodes=("history", "present", "reading", "knowledge"),
        relationships_reviewed=("history->present", "reading->knowledge"),
    )

    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-1",
        whole_graph=graph,
        temporal_context=_temporal(),
        market_reading=_reading(),
        senior_assessment=_assessment(),
        validated_knowledge_ids=("k-1", "k-1", "k-2"),
    )

    assert graph.status is WholeGraphStatus.COMPLETE
    assert cycle.validated_knowledge_ids == ("k-1", "k-2")
    assert cycle.unresolved_questions == ("What changed?",)
    assert cycle.execution_authorized is False


def test_conflicting_reading_stays_unresolved_and_adds_investigation_question() -> None:
    graph = WholeGraphObservationBoundary().audit(
        context_id="cycle-2",
        available_nodes=("history", "present", "reading"),
        observed_nodes=("history", "present", "reading"),
    )
    cycle = SeniorContextCycleBoundary().assemble(
        cycle_id="cycle-2",
        whole_graph=graph,
        temporal_context=_temporal(),
        market_reading=_reading(ReadingStatus.CONFLICTING),
        senior_assessment=_assessment(),
    )

    assert "What evidence is still needed to resolve the reading?" in cycle.unresolved_questions
    assert cycle.execution_authorized is False


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
        )
