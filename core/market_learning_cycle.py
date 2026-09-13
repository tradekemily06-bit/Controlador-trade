from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class EvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


class KnowledgeKind(str, Enum):
    USER_KNOWLEDGE = "USER_KNOWLEDGE"
    SYSTEM_KNOWLEDGE = "SYSTEM_KNOWLEDGE"
    DISCOVERY = "DISCOVERY"


@dataclass(frozen=True)
class MarketEvidence:
    """Auditable evidence; it is not itself an order signal."""

    evidence_id: str
    statement: str
    status: EvidenceStatus
    strength: float
    source: str

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.statement or not self.source:
            raise ValueError("evidence identity, statement and source are required")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("evidence strength must be between 0 and 1")


@dataclass(frozen=True)
class LearningAssessment:
    knowledge_id: str
    kind: KnowledgeKind
    conclusion: EvidenceStatus
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    unanswered_questions: tuple[str, ...]
    test_required: bool
    memory_required: bool
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.knowledge_id:
            raise ValueError("knowledge_id is required")
        if self.execution_authorized:
            raise ValueError("learning assessment cannot authorize execution")


def assess_learning(
    knowledge_id: str,
    kind: KnowledgeKind,
    evidence: Iterable[MarketEvidence],
    questions: Iterable[str] = (),
) -> LearningAssessment:
    """Compare a hypothesis/knowledge item with observed evidence.

    This deliberately does not encode trading concepts as fixed rules. It only
    aggregates evidence supplied by the analysis layer and preserves uncertainty.
    Promotion to validated knowledge must happen through the ecosystem tests and
    validation pipeline, while execution remains separately gated.
    """
    items = tuple(evidence)
    supporting = tuple(e.evidence_id for e in items if e.status is EvidenceStatus.SUPPORTED)
    contradicting = tuple(e.evidence_id for e in items if e.status is EvidenceStatus.CONTRADICTED)
    questions_tuple = tuple(q for q in questions if q)

    if supporting and contradicting:
        conclusion = EvidenceStatus.CONFLICTING
    elif supporting:
        conclusion = EvidenceStatus.SUPPORTED
    elif contradicting:
        conclusion = EvidenceStatus.CONTRADICTED
    else:
        conclusion = EvidenceStatus.INSUFFICIENT

    # Learning never skips the ecosystem's validation/tests or memory layer.
    return LearningAssessment(
        knowledge_id=knowledge_id,
        kind=kind,
        conclusion=conclusion,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        unanswered_questions=questions_tuple,
        test_required=True,
        memory_required=True,
    )
