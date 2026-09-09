from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p85_trusted_knowledge_release import TrustedKnowledgeRelease


class ReleaseAuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class KnowledgeReleaseAudit:
    audit_id: str
    knowledge_id: str
    decision_id: str
    result_id: str
    hypothesis_id: str
    status: ReleaseAuditStatus
    rationale: str


class KnowledgeReleaseAuditBoundary:
    def audit(self, release: TrustedKnowledgeRelease | None, *, audit_id: str, rationale: str) -> KnowledgeReleaseAudit:
        if not isinstance(release, TrustedKnowledgeRelease):
            raise ValueError("invalid trusted knowledge release")
        if not isinstance(audit_id, str) or not audit_id.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("audit_id and rationale are required")
        complete = all(isinstance(v, str) and v.strip() for v in (release.knowledge_id, release.promotion_admission_id, release.decision_id, release.result_id, release.hypothesis_id, release.statement))
        status = ReleaseAuditStatus.VERIFIED if complete and release.real_execution_allowed is False else ReleaseAuditStatus.BLOCKED
        return KnowledgeReleaseAudit(audit_id=audit_id.strip(), knowledge_id=release.knowledge_id, decision_id=release.decision_id, result_id=release.result_id, hypothesis_id=release.hypothesis_id, status=status, rationale=rationale.strip())