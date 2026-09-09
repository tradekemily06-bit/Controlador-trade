from __future__ import annotations

from dataclasses import dataclass

from core.p54_learning_validation import LearningValidation, ValidationStatus


@dataclass(frozen=True)
class TrustedKnowledge:
    knowledge_id: str
    hypothesis_id: str
    test_id: str
    statement: str
    source_observation: str


class TrustedKnowledgeBoundary:
    """Promotes only explicit P54 validation to traceable knowledge."""

    def promote(
        self,
        validation: LearningValidation | None,
        *,
        knowledge_id: str,
        statement: str,
    ) -> TrustedKnowledge:
        if not isinstance(validation, LearningValidation):
            raise ValueError("invalid learning validation")
        if validation.status is not ValidationStatus.VALIDATED:
            raise ValueError("only validated hypotheses can become trusted knowledge")
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            raise ValueError("knowledge_id is required")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("knowledge statement is required")
        return TrustedKnowledge(
            knowledge_id=knowledge_id.strip(),
            hypothesis_id=validation.hypothesis_id,
            test_id=validation.test_id,
            statement=statement.strip(),
            source_observation=validation.observation,
        )
