"""Senior end-to-end contextual cycle boundary.

This layer composes already validated observations without turning the ecosystem
into a catalogue of rigid trading rules. It is decision-neutral: observation,
context, reasoning, validation, memory and risk assessment remain separate from
execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from core.integrated_market_reading import IntegratedMarketReading, ReadingStatus
from core.senior_market_intelligence import SeniorIntelligenceAssessment
from core.senior_market_reasoning import SeniorMarketAssessment
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment
from core.temporal_market_context import TemporalMarketContext
from core.whole_graph_observation import WholeGraphObservation, WholeGraphStatus


class SeniorContextQuality(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    REASSESS = "REASSESS"


@dataclass(frozen=True)
class SeniorContextCycle:
    """Immutable record of one senior contextual reasoning cycle."""

    cycle_id: str
    whole_graph: WholeGraphObservation
    temporal_context: TemporalMarketContext
    market_reading: IntegratedMarketReading
    senior_assessment: SeniorMarketAssessment
    risk_assessment: SeniorRiskAssessment
    validated_knowledge_ids: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    quality: SeniorContextQuality
    intelligence: SeniorIntelligenceAssessment | None = None
    execution_authorized: bool = False


class SeniorContextCycleBoundary:
    """Assemble a traceable senior cycle while failing closed on missing context."""

    def assemble(
        self,
        *,
        cycle_id: str,
        whole_graph: WholeGraphObservation,
        temporal_context: TemporalMarketContext,
        market_reading: IntegratedMarketReading,
        senior_assessment: SeniorMarketAssessment,
        risk_assessment: SeniorRiskAssessment,
        validated_knowledge_ids: Iterable[str] = (),
        intelligence: SeniorIntelligenceAssessment | None = None,
    ) -> SeniorContextCycle:
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id is required")
        if not isinstance(whole_graph, WholeGraphObservation):
            raise ValueError("whole_graph is required")
        if not isinstance(temporal_context, TemporalMarketContext):
            raise ValueError("temporal_context is required")
        if not isinstance(market_reading, IntegratedMarketReading):
            raise ValueError("market_reading is required")
        if not isinstance(senior_assessment, SeniorMarketAssessment):
            raise ValueError("senior_assessment is required")
        if not isinstance(risk_assessment, SeniorRiskAssessment):
            raise ValueError("risk_assessment is required")
        if intelligence is not None and not isinstance(intelligence, SeniorIntelligenceAssessment):
            raise ValueError("intelligence must be SeniorIntelligenceAssessment when provided")
        if senior_assessment.execution_authorized:
            raise ValueError("senior assessment cannot authorize execution")
        if risk_assessment.execution_authorized:
            raise ValueError("risk assessment cannot authorize execution")

        knowledge = self._normalize_ids(validated_knowledge_ids)
        questions = tuple(
            dict.fromkeys(
                question.question.strip()
                for question in senior_assessment.questions
                if isinstance(question.question, str) and question.question.strip()
            )
        )

        if whole_graph.status is WholeGraphStatus.INSUFFICIENT:
            raise ValueError("insufficient whole-graph context")
        if market_reading.status is ReadingStatus.INSUFFICIENT:
            raise ValueError("insufficient market reading")

        if market_reading.status is not ReadingStatus.SUPPORTED:
            questions = tuple(dict.fromkeys((*questions, "What evidence is still needed to resolve the reading?")))

        if risk_assessment.status is not RiskKnowledgeStatus.ASSESSED:
            questions = tuple(
                dict.fromkeys(
                    (*questions, "What material risk information is still missing or requires reassessment (risk/risco)?")
                )
            )

        quality = SeniorContextQuality.COMPLETE
        if whole_graph.status is WholeGraphStatus.PARTIAL:
            quality = SeniorContextQuality.PARTIAL
        if market_reading.status is not ReadingStatus.SUPPORTED or risk_assessment.status is not RiskKnowledgeStatus.ASSESSED:
            quality = SeniorContextQuality.REASSESS

        return SeniorContextCycle(
            cycle_id=cycle_id.strip(),
            whole_graph=whole_graph,
            temporal_context=temporal_context,
            market_reading=market_reading,
            senior_assessment=senior_assessment,
            risk_assessment=risk_assessment,
            validated_knowledge_ids=knowledge,
            unresolved_questions=questions,
            quality=quality,
            execution_authorized=False,
        )

    @staticmethod
    def _normalize_ids(values: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("validated_knowledge_ids must contain non-empty strings")
            value = value.strip()
            if value not in result:
                result.append(value)
        return tuple(result)
