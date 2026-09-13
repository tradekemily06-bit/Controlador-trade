from __future__ import annotations

from dataclasses import dataclass

from core.p55_trusted_knowledge import TrustedKnowledge


@dataclass(frozen=True)
class ValidatedKnowledgeContext:
    """Contextual view of knowledge already validated by the existing P55 boundary.

    This is context, not a signal, score, strategy rule, or execution authority.
    Multiple validated knowledge items are preserved together so the reader can
    interpret relationships without treating each item as an independent vote.
    """

    context_id: str
    knowledge: tuple[TrustedKnowledge, ...]
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.context_id, str) or not self.context_id.strip():
            raise ValueError("context_id is required")
        if not self.knowledge:
            raise ValueError("at least one validated knowledge item is required")
        if any(not isinstance(item, TrustedKnowledge) for item in self.knowledge):
            raise ValueError("all knowledge items must be TrustedKnowledge")
        ids = [item.knowledge_id for item in self.knowledge]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge items must be unique")
        if self.execution_authorized:
            raise ValueError("validated knowledge cannot authorize execution")

    @property
    def statements(self) -> tuple[str, ...]:
        return tuple(item.statement for item in self.knowledge)

    @property
    def knowledge_ids(self) -> tuple[str, ...]:
        return tuple(item.knowledge_id for item in self.knowledge)


class ValidatedKnowledgeContextBoundary:
    """Compose validated knowledge into one contextual, traceable input."""

    def compose(
        self,
        knowledge: tuple[TrustedKnowledge, ...] | list[TrustedKnowledge],
        *,
        context_id: str,
    ) -> ValidatedKnowledgeContext:
        if not isinstance(knowledge, (tuple, list)):
            raise ValueError("knowledge must be a tuple or list")
        return ValidatedKnowledgeContext(
            context_id=context_id.strip() if isinstance(context_id, str) else context_id,
            knowledge=tuple(knowledge),
            execution_authorized=False,
        )
