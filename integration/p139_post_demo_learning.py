"""Compose the factual DEMO closure -> outcome -> reconciliation -> learning path.

This boundary deliberately accepts the outcome as an explicit observation. It
never derives a WIN/LOSS, fetches broker state, changes a decision, or grants
execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operation_learning_journal import OperationLearningNote
from core.p128_learning_handoff import OperationLearningHandoff
from core.p47_automation_closure import AutomationClosure
from core.p48_automation_outcome import AutomationOutcome, AutomationOutcomeBoundary
from core.p49_outcome_reconciliation import (
    ExternalOutcomeObservation,
    OutcomeReconciliation,
    OutcomeReconciliationBoundary,
)
from core.p50_automation_result_snapshot import (
    AutomationResultSnapshot,
    AutomationResultSnapshotBoundary,
)
from integration.p138_result_learning_bridge import ResultLearningBridge


@dataclass(frozen=True)
class PostDemoLearningResult:
    """Immutable post-operation artifacts with no execution authority."""

    outcome: AutomationOutcome
    reconciliation: OutcomeReconciliation
    snapshot: AutomationResultSnapshot
    handoff: OperationLearningHandoff
    execution_authorized: bool = False


class PostDemoLearningBoundary:
    """Close the factual post-DEMO lifecycle without inventing outcome data."""

    def __init__(self, *, learning: ResultLearningBridge | None = None) -> None:
        self.learning = learning or ResultLearningBridge()

    def process(
        self,
        *,
        closure: AutomationClosure,
        observed_at: datetime,
        outcome: Literal["WIN", "LOSS", "DRAW", "UNKNOWN"],
        financial_result: float | None,
        external_observation: ExternalOutcomeObservation | None,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
        note_id: str,
        what_happened: str,
        why_assessment: str,
        evidence: tuple[str, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> PostDemoLearningResult:
        automation_outcome = AutomationOutcomeBoundary().record(
            closure,
            observed_at=observed_at,
            outcome=outcome,
            financial_result=financial_result,
        )
        reconciliation = OutcomeReconciliationBoundary().reconcile(
            automation_outcome,
            external_observation,
        )
        snapshot = AutomationResultSnapshotBoundary().compose(
            closure,
            automation_outcome,
            reconciliation,
        )
        handoff = self.learning.build(
            snapshot=snapshot,
            analysis=analysis,
            market_context=market_context,
            note_id=note_id,
            what_happened=what_happened,
            why_assessment=why_assessment,
            evidence=evidence,
            lessons=lessons,
        )
        return PostDemoLearningResult(
            outcome=automation_outcome,
            reconciliation=reconciliation,
            snapshot=snapshot,
            handoff=handoff,
            execution_authorized=False,
        )
