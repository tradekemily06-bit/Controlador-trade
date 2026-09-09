from __future__ import annotations

from dataclasses import dataclass

from core.p100_operational_feedback_audit import OperationalFeedbackAudit


@dataclass(frozen=True)
class OperationalFeedbackArchive:
    archive_id: str
    audit_id: str
    closure_id: str
    admission_id: str
    disposition_id: str
    assessment_id: str
    observation_id: str
    status: str = "ARCHIVED"
    real_execution_allowed: bool = False


class OperationalFeedbackArchiveBoundary:
    def archive(
        self,
        audit: OperationalFeedbackAudit | None,
        *,
        archive_id: str,
    ) -> OperationalFeedbackArchive:
        if not isinstance(audit, OperationalFeedbackAudit):
            raise ValueError("invalid operational feedback audit")
        if audit.status != "VERIFIED":
            raise ValueError("operational feedback audit must be VERIFIED")
        if not isinstance(archive_id, str) or not archive_id.strip():
            raise ValueError("archive_id is required")
        return OperationalFeedbackArchive(
            archive_id=archive_id.strip(),
            audit_id=audit.audit_id,
            closure_id=audit.closure_id,
            admission_id=audit.admission_id,
            disposition_id=audit.disposition_id,
            assessment_id=audit.assessment_id,
            observation_id=audit.observation_id,
        )
