from __future__ import annotations

from dataclasses import dataclass

from core.p90_controlled_knowledge_use import ControlledKnowledgeUse


@dataclass(frozen=True)
class KnowledgeUseObservation:
    observation_id: str
    use_id: str
    authorization_id: str
    knowledge_id: str
    hypothesis_id: str
    sample_size: int
    observation: str


class KnowledgeUseObservationBoundary:
    def record(self, use: ControlledKnowledgeUse | None, *, observation_id: str, sample_size: int, observation: str) -> KnowledgeUseObservation:
        if not isinstance(use, ControlledKnowledgeUse):
            raise ValueError("invalid controlled knowledge use")
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ValueError("observation_id is required")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("observation is required")
        return KnowledgeUseObservation(observation_id=observation_id.strip(), use_id=use.use_id, authorization_id=use.authorization_id, knowledge_id=use.knowledge_id, hypothesis_id=use.hypothesis_id, sample_size=sample_size, observation=observation.strip())
