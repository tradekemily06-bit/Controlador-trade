from __future__ import annotations

from dataclasses import dataclass

from core.p57_knowledge_memory import KnowledgeMemoryRecord
from core.p58_memory_audit import MemoryAuditDecision, MemoryAuditStatus


@dataclass(frozen=True)
class KnowledgeLabRun:
    lab_id: str
    memory_id: str
    hypothesis_id: str
    scenario: str


class KnowledgeLabBoundary:
    def run(self, audit: MemoryAuditDecision | None, record: KnowledgeMemoryRecord | None, *, lab_id: str, scenario: str) -> KnowledgeLabRun:
        if not isinstance(audit, MemoryAuditDecision) or not isinstance(record, KnowledgeMemoryRecord):
            raise ValueError("invalid lab inputs")
        if audit.status is not MemoryAuditStatus.AUDITABLE or audit.memory_id != record.memory_id:
            raise ValueError("memory record is not auditable")
        if not isinstance(lab_id, str) or not lab_id.strip():
            raise ValueError("lab_id is required")
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError("scenario is required")
        return KnowledgeLabRun(lab_id.strip(), record.memory_id, record.hypothesis_id, scenario.strip())
