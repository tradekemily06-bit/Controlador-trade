"""Senior end-to-end contextual cycle boundary.

This layer composes already validated observations without turning the ecosystem
into a catalogue of rigid trading rules. It is intentionally decision-neutral:
observation, context, reasoning, validation and memory remain separate from
execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.integrated_market_reading import IntegratedMarketReading, ReadingStatus
from core.senior_market_reasoning import SeniorMarketAssessment
from core.temporal_market_context import TemporalMarketContext
from core.whole_graph_observation import WholeGraphObservation, WholeGraphStatus


@dataclass(frozen=True)
class SeniorContextCycle:
    """Immutable record of one complete senior contextual reasoning cycle."""

    cycle_id: str
    whole_graph: WholeGraphObservation
    temporal_context: TemporalMarketContext
    market_reading: IntegratedMarketReading
    senior_assessment: SeniorMarketAssessment
    validated_knowledge_ids: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    execution_authorized: bool = False


class SeniorContextCycleBoundary:
    """Assemble a traceable cycle while failing closed on missing context.

    The boundary does not decide trades and cannot authorize execution. A
    partial whole-graph observation is preserved, while an insufficient graph
    prevents the cycle from being represented as complete.
    """

    def assemble(
        self,
        *,
        cycle_id: str,
        whole_graph: WholeGraphObservation,
        temporal_context: TemporalMarketContext,
        market_reading: IntegratedMarketReading,
        senior_assessment: SeniorMarketAssessment,
        validated_knowledge_ids: Iterable[str] = (),
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

        knowledge = self._normalize_ids(validated_knowledge_ids)
        questions = tuple(
            dict.fromkeys(
                question.question.strip()
                for question in senior_assessment.questions
                if isinstance(question.question, str) and question.question.strip()
            )
        )

        # An insufficient graph must never be represented as a complete cycle.
        if whole_graph.status is WholeGraphStatus.INSUFFICIENT:
            raise ValueError("insufficient whole-graph context")

        # Conflicting/insufficient readings remain unresolved; this is not a
        # failure of the system but an explicit epistemic state.
        if market_reading.status is not ReadingStatus.SUPPORTED:
            questions = tuple(dict.fromkeys((*questions, "What evidence is still needed to resolve the reading?")))

        return SeniorContextCycle(
            cycle_id=cycle_id.strip(),
            whole_graph=whole_graph,
            temporal_context=temporal_context,
            market_reading=market_reading,
            senior_assessment=senior_assessment,
            validated_knowledge_ids=knowledge,
            unresolved_questions=questions,
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
