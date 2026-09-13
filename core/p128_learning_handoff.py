from __future__ import annotations

from dataclasses import dataclass

from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operation_learning_journal import OperationLearningNote
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p51_learning_ingestion import LearningEligibility, LearningIngestionBoundary
from core.p52_learning_evidence import LearningEvidence, LearningEvidenceBoundary


@dataclass(frozen=True)
class OperationLearningHandoff:
    """Complete learning handoff for one operation cycle.

    An operation is never learned as an isolated WIN/LOSS. The handoff keeps the
    observed result together with the reading, market context and investigation
    record. Only reconciled evidence may cross into the learning-evidence layer.
    This artifact cannot authorize execution.
    """

    cycle_id: str
    note: OperationLearningNote
    analysis: AnalysisResult
    market_context: MarketContextResult
    evidence: LearningEvidence | None
    learning_eligible: bool
    execution_authorized: bool = False


class OperationLearningHandoffBoundary:
    """Connects result -> journal -> evidence without creating a parallel learner."""

    def build(
        self,
        *,
        snapshot: AutomationResultSnapshot,
        note: OperationLearningNote,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
    ) -> OperationLearningHandoff:
        if not isinstance(snapshot, AutomationResultSnapshot):
            raise ValueError("invalid automation result snapshot")
        if not isinstance(note, OperationLearningNote):
            raise ValueError("invalid operation learning note")
        if not isinstance(analysis, AnalysisResult):
            raise ValueError("invalid analysis")
        if not isinstance(market_context, MarketContextResult):
            raise ValueError("invalid market context")
        if note.outcome.value != snapshot.outcome and note.outcome.value != "NOT_EXECUTED":
            raise ValueError("operation note outcome does not match result snapshot")

        ingestion = LearningIngestionBoundary().ingest(snapshot)
        evidence = None
        if ingestion.eligibility is LearningEligibility.VERIFIED:
            evidence = LearningEvidenceBoundary().build(ingestion)

        return OperationLearningHandoff(
            cycle_id=snapshot.cycle_id,
            note=note,
            analysis=analysis,
            market_context=market_context,
            evidence=evidence,
            learning_eligible=evidence is not None,
            execution_authorized=False,
        )
