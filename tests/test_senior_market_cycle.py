from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.p55_trusted_knowledge import TrustedKnowledge
from core.senior_market_cycle import SeniorMarketCycleEngine
from core.senior_market_intelligence import SeniorIntelligenceStatus
from core.senior_market_reasoning import ReasoningPosture
from data.models import Candle


def _candles() -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(start + timedelta(minutes=i), 100 + i, 102 + i, 99 + i, 101 + i)
        for i in range(5)
    ]


def test_cycle_observes_context_temporally_and_uses_validated_knowledge() -> None:
    knowledge = TrustedKnowledge(
        knowledge_id="knowledge-1",
        hypothesis_id="hypothesis-1",
        test_id="test-1",
        statement="validated observation",
        source_observation="observation-1",
    )
    cycle = SeniorMarketCycleEngine().assess(
        _candles(),
        context_id="cycle-1",
        available_nodes=("history", "present", "structure", "volatility", "liquidity"),
        observed_nodes=("history", "present", "structure", "volatility", "liquidity"),
        relationships_reviewed=("history->present", "structure->volatility", "structure->liquidity"),
        trusted_knowledge=(knowledge,),
    )

    assert cycle.graph.complete is True
    assert cycle.temporal.historical
    assert cycle.temporal.present
    assert cycle.temporal.scenarios
    assert cycle.intelligence.status is SeniorIntelligenceStatus.READY
    assert cycle.intelligence.knowledge_ids == ("builtin:senior-professional-baseline", "knowledge-1")
    assert cycle.execution_authorized is False


def test_cycle_preserves_partial_context_and_does_not_upgrade_it_to_certainty() -> None:
    cycle = SeniorMarketCycleEngine().assess(
        _candles(),
        context_id="cycle-2",
        available_nodes=("history", "present", "volume"),
        observed_nodes=("history", "present"),
        gaps={"volume": "volume unavailable"},
    )

    assert cycle.graph.complete is False
    assert cycle.intelligence.status is SeniorIntelligenceStatus.PARTIAL
    assert cycle.intelligence.required_reassessment
    assert cycle.execution_authorized is False


def test_cycle_never_uses_senior_layer_as_an_execution_authority() -> None:
    cycle = SeniorMarketCycleEngine().assess(
        _candles(),
        context_id="cycle-3",
        available_nodes=("history", "present"),
        observed_nodes=("history", "present"),
    )

    assert cycle.reasoning.execution_authorized is False
    assert cycle.intelligence.execution_authorized is False
    assert cycle.execution_authorized is False
