from __future__ import annotations

from dataclasses import dataclass

from core.p105_operational_hypothesis_admission import OperationalHypothesisAdmission


@dataclass(frozen=True)
class OperationalHypothesisAudit:
    audit_id: str
    admission_id: str
    hypothesis_id: str
    context_id: str
    readiness_id: str
    status: str = "VERIFIED"
    rationale: str = ""
    real_execution_allowed: bool = False


class OperationalHypothesisAuditBoundary:
    def audit(self, admission: OperationalHypothesisAdmission | None, *, audit_id: str, rationale: str) -> OperationalHypothesisAudit:
        if not isinstance(admission, OperationalHypothesisAdmission):
            raise ValueError("invalid operational hypothesis admission")
        if admission.status != "ADMITTED":
            raise ValueError("operational hypothesis must be ADMITTED")
        if not audit_id.strip() or not rationale.strip():
            raise ValueError("audit_id and rationale are required")
        return OperationalHypothesisAudit(audit_id.strip(), admission.admission_id, admission.hypothesis_id, admission.context_id, admission.readiness_id, rationale=rationale.strip())
