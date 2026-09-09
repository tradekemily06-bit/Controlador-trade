from __future__ import annotations

from dataclasses import dataclass

from core.p51_learning_ingestion import LearningEligibility, LearningIngestionRecord


@dataclass(frozen=True)
class LearningEvidence:
    cycle_id: str
    outcome: str
    financial_result: float | None
    factual: bool = True


class LearningEvidenceBoundary:
    """Promotes verified observations to evidence without creating strategy rules."""

    def build(self, record: LearningIngestionRecord | None) -> LearningEvidence:
        if not isinstance(record, LearningIngestionRecord):
            raise ValueError("invalid learning ingestion record")
        if record.eligibility is not LearningEligibility.VERIFIED:
            raise ValueError("only verified records can become learning evidence")
        if not isinstance(record.cycle_id, str) or not record.cycle_id.strip():
            raise ValueError("cycle_id is required")
        return LearningEvidence(
            cycle_id=record.cycle_id,
            outcome=record.outcome,
            financial_result=record.financial_result,
        )
