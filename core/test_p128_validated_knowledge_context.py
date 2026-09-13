import pytest

from core.p128_validated_knowledge_context import ValidatedKnowledgeContextBoundary
from core.p55_trusted_knowledge import TrustedKnowledge


def _knowledge(knowledge_id: str = "k1") -> TrustedKnowledge:
    return TrustedKnowledge(
        knowledge_id=knowledge_id,
        hypothesis_id="h1",
        test_id="t1",
        statement="Relação validada em contexto específico.",
        source_observation="observação validada",
    )


def test_composes_multiple_validated_items_as_one_context_without_execution_authority():
    context = ValidatedKnowledgeContextBoundary().compose(
        [_knowledge("k1"), _knowledge("k2")],
        context_id="ctx-1",
    )

    assert context.knowledge_ids == ("k1", "k2")
    assert len(context.statements) == 2
    assert context.execution_authorized is False


def test_rejects_duplicate_knowledge_items():
    with pytest.raises(ValueError, match="unique"):
        ValidatedKnowledgeContextBoundary().compose(
            [_knowledge("k1"), _knowledge("k1")],
            context_id="ctx-1",
        )


def test_requires_at_least_one_validated_item():
    with pytest.raises(ValueError, match="at least one"):
        ValidatedKnowledgeContextBoundary().compose([], context_id="ctx-1")


def test_requires_non_empty_context_id():
    with pytest.raises(ValueError, match="context_id"):
        ValidatedKnowledgeContextBoundary().compose([_knowledge()], context_id=" ")
