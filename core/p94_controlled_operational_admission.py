from __future__ import annotations

from dataclasses import dataclass

from core.p93_knowledge_use_disposition import KnowledgeUseDisposition, UseDispositionRecord


@dataclass(frozen=True)
class ControlledOperationalAdmission:
    admission_id: str
    disposition_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    status: str = "ADMITTED"
    real_execution_allowed: bool = False


class ControlledOperationalAdmissionBoundary:
    def admit(self, disposition: UseDispositionRecord | None, *, admission_id: str) -> ControlledOperationalAdmission:
        if not isinstance(disposition, UseDispositionRecord):
            raise ValueError("invalid disposition record")
        if disposition.disposition is not KnowledgeUseDisposition.RETAIN:
            raise ValueError("only retained knowledge use can be admitted")
        if not isinstance(admission_id, str) or not admission_id.strip():
            raise ValueError("admission_id is required")
        return ControlledOperationalAdmission(admission_id=admission_id.strip(), disposition_id=disposition.disposition_id, evaluation_id=disposition.evaluation_id, use_id=disposition.use_id, knowledge_id=disposition.knowledge_id, hypothesis_id=disposition.hypothesis_id, scope="CONTROLLED")
