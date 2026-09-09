from __future__ import annotations

from dataclasses import dataclass

from core.p86_knowledge_release_audit import KnowledgeReleaseAudit, ReleaseAuditStatus


@dataclass(frozen=True)
class ControlledKnowledgeInterpretation:
    interpretation_id: str
    audit_id: str
    knowledge_id: str
    hypothesis_id: str
    interpretation: str
    real_execution_allowed: bool = False


class ControlledKnowledgeInterpretationBoundary:
    def interpret(self, audit: KnowledgeReleaseAudit | None, *, interpretation_id: str, interpretation: str) -> ControlledKnowledgeInterpretation:
        if not isinstance(audit, KnowledgeReleaseAudit) or audit.status is not ReleaseAuditStatus.VERIFIED:
            raise ValueError("knowledge release audit is not verified")
        if not isinstance(interpretation_id, str) or not interpretation_id.strip() or not isinstance(interpretation, str) or not interpretation.strip():
            raise ValueError("interpretation_id and interpretation are required")
        return ControlledKnowledgeInterpretation(interpretation_id=interpretation_id.strip(), audit_id=audit.audit_id, knowledge_id=audit.knowledge_id, hypothesis_id=audit.hypothesis_id, interpretation=interpretation.strip())