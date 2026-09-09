from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p70_adaptation_cycle_closure import AdaptationCycleClosure


class ClosureAuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CycleClosureAudit:
    proposal_id: str
    application_id: str
    observation_id: str
    eligibility: str
    status: ClosureAuditStatus
    rationale: str


class CycleClosureAuditBoundary:
    def audit(
        self,
        closure: AdaptationCycleClosure | None,
        *,
        status: ClosureAuditStatus,
        rationale: str,
    ) -> CycleClosureAudit:
        if not isinstance(closure, AdaptationCycleClosure):
            raise ValueError("invalid cycle closure")
        if not all(isinstance(value, str) and value.strip() for value in (
            closure.proposal_id, closure.application_id, closure.observation_id,
        )):
            raise ValueError("incomplete cycle closure provenance")
        if not isinstance(status, ClosureAuditStatus):
            raise ValueError("invalid closure audit status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("closure audit rationale is required")
        return CycleClosureAudit(
            proposal_id=closure.proposal_id,
            application_id=closure.application_id,
            observation_id=closure.observation_id,
            eligibility=closure.eligibility,
            status=status,
            rationale=rationale.strip(),
        )
