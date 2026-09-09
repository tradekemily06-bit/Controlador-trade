from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p60_adaptation_proposal import AdaptationProposal


class EvaluationStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class AdaptationEvaluation:
    proposal_id: str
    status: EvaluationStatus
    rationale: str


class AdaptationEvaluationBoundary:
    def evaluate(self, proposal: AdaptationProposal | None, *, status: EvaluationStatus, rationale: str) -> AdaptationEvaluation:
        if not isinstance(proposal, AdaptationProposal):
            raise ValueError("invalid adaptation proposal")
        if not isinstance(status, EvaluationStatus):
            raise ValueError("invalid evaluation status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("evaluation rationale is required")
        return AdaptationEvaluation(proposal.proposal_id, status, rationale.strip())
