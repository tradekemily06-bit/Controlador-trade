from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p97_operational_assessment import OperationalAssessment


class OperationalDisposition(str, Enum):
    RETAIN = "RETAIN"
    REVIEW = "REVIEW"
    RETIRE = "RETIRE"


@dataclass(frozen=True)
class OperationalDispositionRecord:
    disposition_id: str
    assessment_id: str
    observation_id: str
    closure_id: str
    admission_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    disposition: OperationalDisposition
    rationale: str
    real_execution_allowed: bool = False


class OperationalDispositionBoundary:
    def decide(
        self,
        assessment: OperationalAssessment | None,
        *,
        disposition_id: str,
        disposition: OperationalDisposition,
        rationale: str,
    ) -> OperationalDispositionRecord:
        if not isinstance(assessment, OperationalAssessment):
            raise ValueError("invalid operational assessment")
        if not isinstance(disposition_id, str) or not disposition_id.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("disposition_id and rationale are required")
        if not isinstance(disposition, OperationalDisposition):
            raise ValueError("invalid operational disposition")
        return OperationalDispositionRecord(
            disposition_id=disposition_id.strip(),
            assessment_id=assessment.assessment_id,
            observation_id=assessment.observation_id,
            closure_id=assessment.closure_id,
            admission_id=assessment.admission_id,
            evaluation_id=assessment.evaluation_id,
            use_id=assessment.use_id,
            knowledge_id=assessment.knowledge_id,
            hypothesis_id=assessment.hypothesis_id,
            disposition=disposition,
            rationale=rationale.strip(),
        )
