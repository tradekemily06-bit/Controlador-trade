from __future__ import annotations

from dataclasses import dataclass

from core.p101_operational_feedback_archive import OperationalFeedbackArchive


@dataclass(frozen=True)
class NextOperationalCycleReadiness:
    readiness_id: str
    archive_id: str
    audit_id: str
    closure_id: str
    status: str
    real_execution_allowed: bool = False


class NextOperationalCycleReadinessBoundary:
    def assess(
        self,
        archive: OperationalFeedbackArchive | None,
        *,
        readiness_id: str,
    ) -> NextOperationalCycleReadiness:
        if not isinstance(archive, OperationalFeedbackArchive):
            raise ValueError("invalid operational feedback archive")
        if archive.status != "ARCHIVED":
            raise ValueError("operational feedback archive must be ARCHIVED")
        if not isinstance(readiness_id, str) or not readiness_id.strip():
            raise ValueError("readiness_id is required")
        return NextOperationalCycleReadiness(
            readiness_id=readiness_id.strip(),
            archive_id=archive.archive_id,
            audit_id=archive.audit_id,
            closure_id=archive.closure_id,
            status="READY",
        )
