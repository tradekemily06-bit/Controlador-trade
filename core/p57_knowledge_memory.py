from __future__ import annotations

from dataclasses import dataclass

from core.p55_trusted_knowledge import TrustedKnowledge


@dataclass(frozen=True)
class KnowledgeMemoryRecord:
    memory_id: str
    knowledge_id: str
    hypothesis_id: str
    test_id: str
    statement: str


class KnowledgeMemoryBoundary:
    def record(self, knowledge: TrustedKnowledge | None, *, memory_id: str) -> KnowledgeMemoryRecord:
        if not isinstance(knowledge, TrustedKnowledge):
            raise ValueError("invalid trusted knowledge")
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError("memory_id is required")
        return KnowledgeMemoryRecord(
            memory_id=memory_id.strip(),
            knowledge_id=knowledge.knowledge_id,
            hypothesis_id=knowledge.hypothesis_id,
            test_id=knowledge.test_id,
            statement=knowledge.statement,
        )
