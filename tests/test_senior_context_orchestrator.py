from datetime import datetime, timedelta, timezone

import pytest

from core.senior_context_orchestrator import SeniorContextInput, SeniorContextOrchestrator
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from core.senior_context_cycle import SeniorContextQuality
from data.models import Candle


def candles(count=5):
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return tuple(
        Candle(
            timestamp=base + timedelta(minutes=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
        )
        for index in range(count)
    )


def request(*, risk_observations=(), available_risk_domains=(RiskDomain.CAPITAL,)):
    return SeniorContextInput(
        context_id="ctx-1",
        candles=candles(),
        available_nodes=("price", "structure", "volatility", "liquidity"),
        observed_nodes=("price", "structure", "volatility", "liquidity"),
        gaps={},
        relationships_reviewed=("price-structure", "structure-volatility", "price-liquidity"),
        risk_observations=tuple(risk_observations),
        validated_knowledge_ids=("knowledge-validated-1",),
        available_risk_domains=tuple(available_risk_domains),
    )


def test_orchestrator_composes_context_without_execution_authority():
    cycle = SeniorContextOrchestrator().assess(
        request(risk_observations=(RiskObservation(RiskDomain.CAPITAL, "Capital observado.", True, ("account",)),))
    )

    assert cycle.quality is SeniorContextQuality.COMPLETE
    assert cycle.whole_graph.complete is True
    assert cycle.temporal_context.present
    assert cycle.market_reading.observations
    assert cycle.senior_assessment.questions
    assert cycle.risk_assessment.questions
    assert cycle.validated_knowledge_ids == ("builtin:senior-professional-baseline", "knowledge-validated-1")
    assert cycle.execution_authorized is False
    assert cycle.senior_assessment.execution_authorized is False
    assert cycle.risk_assessment.execution_authorized is False


def test_orchestrator_keeps_missing_risk_context_in_reassessment():
    cycle = SeniorContextOrchestrator().assess(request())

    assert cycle.quality is SeniorContextQuality.REASSESS
    assert cycle.risk_assessment.status.value == "INSUFFICIENT"
    assert cycle.execution_authorized is False
    assert any("risk" in question.lower() for question in cycle.unresolved_questions)


def test_orchestrator_rejects_invalid_or_unsorted_market_data():
    ordered = candles()
    reversed_candles = tuple(reversed(ordered))
    invalid = SeniorContextInput(
        context_id="ctx-1",
        candles=reversed_candles,
        available_nodes=("price",),
        observed_nodes=("price",),
        gaps={},
        relationships_reviewed=(),
        risk_observations=(),
        available_risk_domains=(RiskDomain.CAPITAL,),
    )

    with pytest.raises(ValueError, match="ordered"):
        SeniorContextOrchestrator().assess(invalid)


def test_orchestrator_does_not_accept_invalid_candle():
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    bad = Candle(base, 100, 90, 95, 98)
    value = SeniorContextInput(
        context_id="ctx-1",
        candles=(bad,),
        available_nodes=("price",),
        observed_nodes=("price",),
        gaps={},
        relationships_reviewed=(),
        risk_observations=(),
        available_risk_domains=(RiskDomain.CAPITAL,),
    )

    with pytest.raises(ValueError, match="valid Candle"):
        SeniorContextOrchestrator().assess(value)
