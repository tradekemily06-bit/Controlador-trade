from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p57_knowledge_memory import KnowledgeMemoryRecord


class MemoryAuditStatus(str, Enum):
    AUDITABLE = "AUDITABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class MemoryAuditDecision:
    memory_id: str
    status: MemoryAuditStatus
    reason: str


class MemoryAuditBoundary:
    def audit(self, record: KnowledgeMemoryRecord | None) -> MemoryAuditDecision:
        if not isinstance(record, KnowledgeMemoryRecord):
            raise ValueError("invalid knowledge memory record")
        fields = (record.memory_id, record.knowledge_id, record.hypothesis_id, record.test_id, record.statement)
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            return MemoryAuditDecision(record.memory_id, MemoryAuditStatus.BLOCKED, "incomplete provenance")
        return MemoryAuditDecision(record.memory_id, MemoryAuditStatus.AUDITABLE, "provenance is complete")
