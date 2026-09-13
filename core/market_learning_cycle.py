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
    evidence: Iterable[MarketEvidence] = (),
    questions: Iterable[str] = (),
) -> LearningAssessment:
    """Compare knowledge or a hypothesis with observed evidence.

    The input is intentionally extensible: user knowledge, system knowledge and
    discoveries can all be assessed without making the user's concepts a closed
    rule set. Evidence is classified conservatively and promotion still requires
    the ecosystem's existing validation/memory pipeline. Execution remains separate.
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
