from __future__ import annotations

from dataclasses import dataclass

from core.p55_trusted_knowledge import TrustedKnowledge


@dataclass(frozen=True)
class ControlledKnowledgeUse:
    knowledge_id: str
    hypothesis_id: str
    test_id: str
    consumer: str
    use_id: str
    real_execution_allowed: bool = False


class ControlledKnowledgeUseBoundary:
    """Makes explicit knowledge eligible for controlled use without executing it."""

    def authorize(
        self,
        knowledge: TrustedKnowledge | None,
        *,
        use_id: str,
        consumer: str,
    ) -> ControlledKnowledgeUse:
        if not isinstance(knowledge, TrustedKnowledge):
            raise ValueError("invalid trusted knowledge")
        if not isinstance(use_id, str) or not use_id.strip():
            raise ValueError("use_id is required")
        if not isinstance(consumer, str) or not consumer.strip():
            raise ValueError("consumer is required")
        return ControlledKnowledgeUse(
            knowledge_id=knowledge.knowledge_id,
            hypothesis_id=knowledge.hypothesis_id,
            test_id=knowledge.test_id,
            consumer=consumer.strip(),
            use_id=use_id.strip(),
            real_execution_allowed=False,
        )
