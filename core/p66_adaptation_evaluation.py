from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p65_adaptation_observation import AdaptationObservation


class PostAdaptationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class PostAdaptationEvaluation:
    proposal_id: str
    application_id: str
    observation_id: str
    status: PostAdaptationStatus
    rationale: str


class PostAdaptationEvaluationBoundary:
    def evaluate(
        self,
        observation: AdaptationObservation | None,
        *,
        status: PostAdaptationStatus,
        rationale: str,
    ) -> PostAdaptationEvaluation:
        if not isinstance(observation, AdaptationObservation):
            raise ValueError("invalid adaptation observation")
        if not isinstance(status, PostAdaptationStatus):
            raise ValueError("invalid post-adaptation status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("evaluation rationale is required")
        return PostAdaptationEvaluation(
            proposal_id=observation.proposal_id,
            application_id=observation.application_id,
            observation_id=observation.observation_id,
            status=status,
            rationale=rationale.strip(),
        )
