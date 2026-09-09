from __future__ import annotations

from dataclasses import dataclass

from core.p66_adaptation_evaluation import PostAdaptationEvaluation


@dataclass(frozen=True)
class AdaptationCycleRecord:
    proposal_id: str
    application_id: str
    observation_id: str
    status: str
    rationale: str


class AdaptationCycleBoundary:
    def consolidate(self, evaluation: PostAdaptationEvaluation | None) -> AdaptationCycleRecord:
        if not isinstance(evaluation, PostAdaptationEvaluation):
            raise ValueError("invalid post-adaptation evaluation")
        return AdaptationCycleRecord(
            proposal_id=evaluation.proposal_id,
            application_id=evaluation.application_id,
            observation_id=evaluation.observation_id,
            status=evaluation.status.value,
            rationale=evaluation.rationale,
        )
