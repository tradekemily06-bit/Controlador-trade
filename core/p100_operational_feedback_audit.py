from __future__ import annotations

from dataclasses import dataclass

from core.p99_operational_feedback_closure import OperationalFeedbackClosure


@dataclass(frozen=True)
class OperationalFeedbackAudit:
    audit_id: str
    closure_id: str
    admission_id: str
    disposition_id: str
    assessment_id: str
    observation_id: str
    status: str
    rationale: str
    real_execution_allowed: bool = False


class OperationalFeedbackAuditBoundary:
    def audit(
        self,
        closure: OperationalFeedbackClosure | None,
        *,
        audit_id: str,
        rationale: str,
    ) -> OperationalFeedbackAudit:
        if not isinstance(closure, OperationalFeedbackClosure):
            raise ValueError("invalid operational feedback closure")
        if closure.status != "CLOSED":
            raise ValueError("operational feedback closure must be CLOSED")
        if not isinstance(audit_id, str) or not audit_id.strip():
            raise ValueError("audit_id is required")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        return OperationalFeedbackAudit(
            audit_id=audit_id.strip(),
            closure_id=closure.closure_id,
            admission_id=closure.admission_id,
            disposition_id=closure.disposition_id,
            assessment_id=closure.assessment_id,
            observation_id=closure.observation_id,
            status="VERIFIED",
            rationale=rationale.strip(),
        )
