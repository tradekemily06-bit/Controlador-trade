from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p49_outcome_reconciliation import ReconciliationState
from core.p50_automation_result_snapshot import AutomationResultSnapshot


class LearningEligibility(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    MISMATCHED = "MISMATCHED"


@dataclass(frozen=True)
class LearningIngestionRecord:
    cycle_id: str
    outcome: str
    financial_result: float | None
    external_result_ids: tuple[str, ...] = ()
    external_reference: str | None = None
    external_container_id: str | None = None
    eligibility: LearningEligibility


class LearningIngestionBoundary:
    """Classifies factual snapshots without turning them into learned knowledge."""

    def ingest(self, snapshot: AutomationResultSnapshot | None) -> LearningIngestionRecord:
        if not isinstance(snapshot, AutomationResultSnapshot):
            raise ValueError("invalid automation result snapshot")
        if not isinstance(snapshot.cycle_id, str) or not snapshot.cycle_id.strip():
            raise ValueError("cycle_id is required")
        eligibility = {
            ReconciliationState.MATCHED: LearningEligibility.VERIFIED,
            ReconciliationState.UNVERIFIED: LearningEligibility.UNVERIFIED,
            ReconciliationState.MISMATCHED: LearningEligibility.MISMATCHED,
        }[snapshot.reconciliation_state]
        return LearningIngestionRecord(
            cycle_id=snapshot.cycle_id,
            outcome=snapshot.outcome,
            financial_result=snapshot.financial_result,
            external_result_ids=snapshot.external_result_ids,
            external_reference=snapshot.external_reference,
            external_container_id=snapshot.external_container_id,
            eligibility=eligibility,
        )
