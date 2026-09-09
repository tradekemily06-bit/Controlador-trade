from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p68_adaptation_disposition import AdaptationDisposition


class Eligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class NextCycleEligibility:
    proposal_id: str
    application_id: str
    observation_id: str
    disposition: str
    eligibility: Eligibility
    rationale: str


class NextCycleEligibilityBoundary:
    def evaluate(
        self,
        disposition: AdaptationDisposition | None,
        *,
        eligibility: Eligibility,
        rationale: str,
    ) -> NextCycleEligibility:
        if not isinstance(disposition, AdaptationDisposition):
            raise ValueError("invalid adaptation disposition")
        if not isinstance(eligibility, Eligibility):
            raise ValueError("invalid eligibility")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("eligibility rationale is required")
        return NextCycleEligibility(
            proposal_id=disposition.proposal_id,
            application_id=disposition.application_id,
            observation_id=disposition.observation_id,
            disposition=disposition.disposition.value,
            eligibility=eligibility,
            rationale=rationale.strip(),
        )
