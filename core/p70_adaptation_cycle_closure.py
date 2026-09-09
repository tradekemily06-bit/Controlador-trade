from __future__ import annotations

from dataclasses import dataclass

from core.p69_cycle_eligibility import NextCycleEligibility


@dataclass(frozen=True)
class AdaptationCycleClosure:
    proposal_id: str
    application_id: str
    observation_id: str
    disposition: str
    eligibility: str
    summary: str
    real_execution_allowed: bool = False


class AdaptationCycleClosureBoundary:
    def close(
        self,
        eligibility: NextCycleEligibility | None,
        *,
        summary: str,
    ) -> AdaptationCycleClosure:
        if not isinstance(eligibility, NextCycleEligibility):
            raise ValueError("invalid next-cycle eligibility")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("closure summary is required")
        return AdaptationCycleClosure(
            proposal_id=eligibility.proposal_id,
            application_id=eligibility.application_id,
            observation_id=eligibility.observation_id,
            disposition=eligibility.disposition,
            eligibility=eligibility.eligibility.value,
            summary=summary.strip(),
        )
