from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p61_adaptation_evaluation import AdaptationEvaluation
from core.p62_controlled_adaptation import AppliedAdaptation


class AuditState(str, Enum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class AdaptationCycleAudit:
    proposal_id: str
    application_id: str
    state: AuditState
    summary: str


class AdaptationCycleAuditBoundary:
    def close(self, evaluation: AdaptationEvaluation | None, application: AppliedAdaptation | None, *, summary: str) -> AdaptationCycleAudit:
        if not isinstance(evaluation, AdaptationEvaluation) or not isinstance(application, AppliedAdaptation):
            raise ValueError("invalid adaptation cycle inputs")
        if evaluation.proposal_id != application.proposal_id:
            raise ValueError("adaptation artifacts do not match")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("audit summary is required")
        return AdaptationCycleAudit(
            proposal_id=evaluation.proposal_id,
            application_id=application.application_id,
            state=AuditState.COMPLETE,
            summary=summary.strip(),
        )
