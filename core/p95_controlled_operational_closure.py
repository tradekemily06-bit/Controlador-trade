from __future__ import annotations

from dataclasses import dataclass

from core.p94_controlled_operational_admission import ControlledOperationalAdmission


@dataclass(frozen=True)
class ControlledOperationalClosure:
    closure_id: str
    admission_id: str
    disposition_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    status: str = "CLOSED"
    real_execution_allowed: bool = False


class ControlledOperationalClosureBoundary:
    def close(self, admission: ControlledOperationalAdmission | None, *, closure_id: str) -> ControlledOperationalClosure:
        if not isinstance(admission, ControlledOperationalAdmission):
            raise ValueError("invalid controlled operational admission")
        if admission.status != "ADMITTED":
            raise ValueError("operational admission is not active")
        if not isinstance(closure_id, str) or not closure_id.strip():
            raise ValueError("closure_id is required")
        return ControlledOperationalClosure(closure_id=closure_id.strip(), admission_id=admission.admission_id, disposition_id=admission.disposition_id, evaluation_id=admission.evaluation_id, use_id=admission.use_id, knowledge_id=admission.knowledge_id, hypothesis_id=admission.hypothesis_id, scope=admission.scope)
