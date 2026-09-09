from __future__ import annotations

from dataclasses import dataclass

from core.p71_cycle_closure_audit import CycleClosureAudit, ClosureAuditStatus


@dataclass(frozen=True)
class CycleArchiveRecord:
    archive_id: str
    proposal_id: str
    application_id: str
    observation_id: str
    eligibility: str
    audit_rationale: str


class CycleArchiveBoundary:
    def archive(
        self,
        audit: CycleClosureAudit | None,
        *,
        archive_id: str,
    ) -> CycleArchiveRecord:
        if not isinstance(audit, CycleClosureAudit):
            raise ValueError("invalid cycle closure audit")
        if audit.status is not ClosureAuditStatus.VERIFIED:
            raise ValueError("only verified cycle closures can be archived")
        if not isinstance(archive_id, str) or not archive_id.strip():
            raise ValueError("archive_id is required")
        return CycleArchiveRecord(
            archive_id=archive_id.strip(),
            proposal_id=audit.proposal_id,
            application_id=audit.application_id,
            observation_id=audit.observation_id,
            eligibility=audit.eligibility,
            audit_rationale=audit.rationale,
        )
