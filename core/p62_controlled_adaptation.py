from __future__ import annotations

from dataclasses import dataclass

from core.p60_adaptation_proposal import AdaptationProposal
from core.p61_adaptation_evaluation import AdaptationEvaluation, EvaluationStatus


@dataclass(frozen=True)
class AppliedAdaptation:
    proposal_id: str
    application_id: str
    rationale: str
    real_execution_allowed: bool = False


class ControlledAdaptationBoundary:
    def apply(self, proposal: AdaptationProposal | None, evaluation: AdaptationEvaluation | None, *, application_id: str) -> AppliedAdaptation:
        if not isinstance(proposal, AdaptationProposal) or not isinstance(evaluation, AdaptationEvaluation):
            raise ValueError("invalid adaptation inputs")
        if evaluation.proposal_id != proposal.proposal_id:
            raise ValueError("proposal and evaluation do not match")
        if evaluation.status is not EvaluationStatus.APPROVED:
            raise ValueError("only approved adaptations can be applied")
        if proposal.applied:
            raise ValueError("adaptation proposal is already applied")
        if not isinstance(application_id, str) or not application_id.strip():
            raise ValueError("application_id is required")
        return AppliedAdaptation(
            proposal_id=proposal.proposal_id,
            application_id=application_id.strip(),
            rationale=evaluation.rationale,
        )
