from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p91_knowledge_use_observation import KnowledgeUseObservation


class KnowledgeUseEvaluationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class KnowledgeUseEvaluation:
    evaluation_id: str
    observation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    status: KnowledgeUseEvaluationStatus
    rationale: str


class KnowledgeUseEvaluationBoundary:
    def evaluate(self, observation: KnowledgeUseObservation | None, *, evaluation_id: str, status: KnowledgeUseEvaluationStatus, rationale: str) -> KnowledgeUseEvaluation:
        if not isinstance(observation, KnowledgeUseObservation):
            raise ValueError("invalid knowledge use observation")
        if not isinstance(evaluation_id, str) or not evaluation_id.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("evaluation_id and rationale are required")
        if not isinstance(status, KnowledgeUseEvaluationStatus):
            raise ValueError("invalid evaluation status")
        return KnowledgeUseEvaluation(evaluation_id=evaluation_id.strip(), observation_id=observation.observation_id, use_id=observation.use_id, knowledge_id=observation.knowledge_id, hypothesis_id=observation.hypothesis_id, status=status, rationale=rationale.strip())
