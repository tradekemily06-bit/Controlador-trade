from __future__ import annotations

from dataclasses import dataclass

from core.p98_operational_disposition import OperationalDispositionRecord


@dataclass(frozen=True)
class OperationalFeedbackClosure:
    closure_id: str
    disposition_id: str
    assessment_id: str
    observation_id: str
    operational_closure_id: str
    admission_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    disposition: str
    status: str = "CLOSED"
    real_execution_allowed: bool = False


class OperationalFeedbackClosureBoundary:
    def close(
        self,
        disposition: OperationalDispositionRecord | None,
        *,
        closure_id: str,
    ) -> OperationalFeedbackClosure:
        if not isinstance(disposition, OperationalDispositionRecord):
            raise ValueError("invalid operational disposition")
        if not isinstance(closure_id, str) or not closure_id.strip():
            raise ValueError("closure_id is required")
        return OperationalFeedbackClosure(
            closure_id=closure_id.strip(),
            disposition_id=disposition.disposition_id,
            assessment_id=disposition.assessment_id,
            observation_id=disposition.observation_id,
            operational_closure_id=disposition.closure_id,
            admission_id=disposition.admission_id,
            evaluation_id=disposition.evaluation_id,
            use_id=disposition.use_id,
            knowledge_id=disposition.knowledge_id,
            hypothesis_id=disposition.hypothesis_id,
            disposition=disposition.disposition.value,
        )
