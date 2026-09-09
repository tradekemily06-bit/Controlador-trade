from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p92_knowledge_use_evaluation import KnowledgeUseEvaluation


class KnowledgeUseDisposition(str, Enum):
    RETAIN = "RETAIN"
    REVIEW = "REVIEW"
    RETIRE = "RETIRE"


@dataclass(frozen=True)
class UseDispositionRecord:
    disposition_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    disposition: KnowledgeUseDisposition
    rationale: str


class KnowledgeUseDispositionBoundary:
    def decide(self, evaluation: KnowledgeUseEvaluation | None, *, disposition_id: str, disposition: KnowledgeUseDisposition, rationale: str) -> UseDispositionRecord:
        if not isinstance(evaluation, KnowledgeUseEvaluation):
            raise ValueError("invalid knowledge use evaluation")
        if not isinstance(disposition_id, str) or not disposition_id.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("disposition_id and rationale are required")
        if not isinstance(disposition, KnowledgeUseDisposition):
            raise ValueError("invalid disposition")
        return UseDispositionRecord(disposition_id=disposition_id.strip(), evaluation_id=evaluation.evaluation_id, use_id=evaluation.use_id, knowledge_id=evaluation.knowledge_id, hypothesis_id=evaluation.hypothesis_id, disposition=disposition, rationale=rationale.strip())
