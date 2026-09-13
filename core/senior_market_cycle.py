"""End-to-end senior contextual reasoning cycle.

The cycle deliberately composes existing boundaries instead of replacing them:
whole-graph audit -> temporal context -> integrated reading -> senior posture ->
senior-grade knowledge standard. It remains analysis-only and cannot authorize
execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from data.models import Candle

from .integrated_market_reading import IntegratedMarketReader, IntegratedMarketReading
from .p55_trusted_knowledge import TrustedKnowledge
from .senior_market_intelligence import (
    DEFAULT_SENIOR_KNOWLEDGE_STANDARD,
    SeniorIntelligenceAssessment,
    SeniorKnowledgeStandard,
    SeniorMarketIntelligenceBoundary,
)
from .senior_market_reasoning import SeniorMarketAssessment, SeniorMarketReasoner
from .temporal_market_context import TemporalMarketContext, TemporalMarketContextEngine
from .whole_graph_observation import WholeGraphObservation, WholeGraphObservationBoundary


@dataclass(frozen=True)
class SeniorMarketCycle:
    graph: WholeGraphObservation
    temporal: TemporalMarketContext
    reading: IntegratedMarketReading
    reasoning: SeniorMarketAssessment
    intelligence: SeniorIntelligenceAssessment
    execution_authorized: bool = False


class SeniorMarketCycleEngine:
    """Run the complete senior reasoning posture for one market observation cycle."""

    def __init__(
        self,
        *,
        graph_boundary: WholeGraphObservationBoundary | None = None,
        temporal_engine: TemporalMarketContextEngine | None = None,
        reader: IntegratedMarketReader | None = None,
        reasoner: SeniorMarketReasoner | None = None,
        intelligence: SeniorMarketIntelligenceBoundary | None = None,
    ) -> None:
        self.graph_boundary = graph_boundary or WholeGraphObservationBoundary()
        self.temporal_engine = temporal_engine or TemporalMarketContextEngine()
        self.reader = reader or IntegratedMarketReader()
        self.reasoner = reasoner or SeniorMarketReasoner()
        self.intelligence = intelligence or SeniorMarketIntelligenceBoundary()

    def assess(
        self,
        candles: list[Candle],
        *,
        context_id: str,
        available_nodes: Iterable[str],
        observed_nodes: Iterable[str],
        gaps: Mapping[str, str] | None = None,
        relationships_reviewed: Iterable[str] = (),
        trusted_knowledge: Iterable[TrustedKnowledge] = (),
        standard: SeniorKnowledgeStandard = DEFAULT_SENIOR_KNOWLEDGE_STANDARD,
    ) -> SeniorMarketCycle:
        graph = self.graph_boundary.audit(
            context_id=context_id,
            available_nodes=available_nodes,
            observed_nodes=observed_nodes,
            gaps=gaps,
            relationships_reviewed=relationships_reviewed,
        )
        temporal = self.temporal_engine.analyze(candles)
        reading = self.reader.read(candles)
        reasoning = self.reasoner.assess(candles, reading, temporal)
        intelligence = self.intelligence.assess(
            graph=graph,
            trusted_knowledge=trusted_knowledge,
            standard=standard,
        )

        # This cycle is intentionally downstream of observation and knowledge
        # validation, but upstream of operational/risk execution gates.
        return SeniorMarketCycle(
            graph=graph,
            temporal=temporal,
            reading=reading,
            reasoning=reasoning,
            intelligence=intelligence,
            execution_authorized=False,
        )
