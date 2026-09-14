"""Application boundary from reconciled DEMO result to operational learning.

This adapter composes the existing P128 learning handoff. It does not create
strategy rules, alter decisions, or grant execution authority.
"""

from __future__ import annotations

from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operation_learning_journal import (
    OperationLearningJournal,
    OperationLearningNote,
    OperationOutcome,
)
from core.p128_learning_handoff import OperationLearningHandoff, OperationLearningHandoffBoundary
from core.p50_automation_result_snapshot import AutomationResultSnapshot


class ResultLearningBridge:
    """Close result -> investigation -> evidence handoff without parallel logic."""

    def __init__(
        self,
        *,
        journal: OperationLearningJournal | None = None,
        handoff: OperationLearningHandoffBoundary | None = None,
    ) -> None:
        self.journal = journal or OperationLearningJournal()
        self.handoff = handoff or OperationLearningHandoffBoundary()

    def build(
        self,
        *,
        snapshot: AutomationResultSnapshot,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
        note_id: str,
        what_happened: str,
        why_assessment: str,
        evidence: tuple[str, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> OperationLearningHandoff:
        if not isinstance(snapshot, AutomationResultSnapshot):
            raise ValueError("invalid automation result snapshot")
        if not isinstance(analysis, AnalysisResult):
            raise ValueError("invalid analysis")
        if not isinstance(market_context, MarketContextResult):
            raise ValueError("invalid market context")

        try:
            outcome = OperationOutcome(snapshot.outcome)
        except ValueError as exc:
            raise ValueError("unknown operation outcome cannot enter learning") from exc

        note = self.journal.create_note(
            note_id=note_id,
            outcome=outcome,
            what_happened=what_happened,
            why_assessment=why_assessment,
            market_context=market_context.reason,
            evidence=evidence,
            questions=self.journal.default_questions(outcome),
            lessons=lessons,
        )
        return self.handoff.build(
            snapshot=snapshot,
            note=note,
            analysis=analysis,
            market_context=market_context,
        )
