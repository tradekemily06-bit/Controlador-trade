from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p67_adaptation_cycle import AdaptationCycleRecord


class Disposition(str, Enum):
    RETAIN = "RETAIN"
    REVIEW = "REVIEW"
    RETIRE = "RETIRE"


@dataclass(frozen=True)
class AdaptationDisposition:
    proposal_id: str
    application_id: str
    observation_id: str
    disposition: Disposition
    rationale: str


class AdaptationDispositionBoundary:
    def decide(
        self,
        cycle: AdaptationCycleRecord | None,
        *,
        disposition: Disposition,
        rationale: str,
    ) -> AdaptationDisposition:
        if not isinstance(cycle, AdaptationCycleRecord):
            raise ValueError("invalid adaptation cycle")
        if not isinstance(disposition, Disposition):
            raise ValueError("invalid disposition")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("disposition rationale is required")
        return AdaptationDisposition(
            proposal_id=cycle.proposal_id,
            application_id=cycle.application_id,
            observation_id=cycle.observation_id,
            disposition=disposition,
            rationale=rationale.strip(),
        )
