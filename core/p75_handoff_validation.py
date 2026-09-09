from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p74_next_cycle_handoff import NextCycleHandoff


class HandoffValidationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class HandoffValidation:
    handoff_id: str
    archive_id: str
    proposal_id: str
    application_id: str
    observation_id: str
    status: HandoffValidationStatus
    rationale: str


class HandoffValidationBoundary:
    def validate(
        self,
        handoff: NextCycleHandoff | None,
        *,
        status: HandoffValidationStatus,
        rationale: str,
    ) -> HandoffValidation:
        if not isinstance(handoff, NextCycleHandoff):
            raise ValueError("invalid next-cycle handoff")
        values = (handoff.handoff_id, handoff.archive_id, handoff.proposal_id,
                  handoff.application_id, handoff.observation_id)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("incomplete handoff provenance")
        if not isinstance(status, HandoffValidationStatus):
            raise ValueError("invalid handoff validation status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("validation rationale is required")
        return HandoffValidation(
            handoff_id=handoff.handoff_id,
            archive_id=handoff.archive_id,
            proposal_id=handoff.proposal_id,
            application_id=handoff.application_id,
            observation_id=handoff.observation_id,
            status=status,
            rationale=rationale.strip(),
        )
