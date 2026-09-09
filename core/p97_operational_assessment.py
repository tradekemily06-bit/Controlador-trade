from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p96_operational_observation import OperationalObservation


class OperationalAssessmentStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class OperationalAssessment:
    assessment_id: str
    observation_id: str
    closure_id: str
    admission_id: str
    disposition_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    status: OperationalAssessmentStatus
    rationale: str


class OperationalAssessmentBoundary:
    def assess(
        self,
        observation: OperationalObservation | None,
        *,
        assessment_id: str,
        status: OperationalAssessmentStatus,
        rationale: str,
    ) -> OperationalAssessment:
        if not isinstance(observation, OperationalObservation):
            raise ValueError("invalid operational observation")
        if not isinstance(assessment_id, str) or not assessment_id.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("assessment_id and rationale are required")
        if not isinstance(status, OperationalAssessmentStatus):
            raise ValueError("invalid operational assessment status")
        return OperationalAssessment(
            assessment_id=assessment_id.strip(),
            observation_id=observation.observation_id,
            closure_id=observation.closure_id,
            admission_id=observation.admission_id,
            disposition_id=observation.disposition_id,
            evaluation_id=observation.evaluation_id,
            use_id=observation.use_id,
            knowledge_id=observation.knowledge_id,
            hypothesis_id=observation.hypothesis_id,
            status=status,
            rationale=rationale.strip(),
        )
