from __future__ import annotations

from dataclasses import dataclass

from core.p52_learning_evidence import LearningEvidence


@dataclass(frozen=True)
class LearningHypothesis:
    hypothesis_id: str
    evidence_cycle_id: str
    statement: str
    validated: bool = False


class LearningHypothesisBoundary:
    """Creates explicit testable hypotheses; it never validates or operationalizes them."""

    def propose(
        self,
        evidence: LearningEvidence | None,
        *,
        hypothesis_id: str,
        statement: str,
    ) -> LearningHypothesis:
        if not isinstance(evidence, LearningEvidence):
            raise ValueError("invalid learning evidence")
        if not evidence.factual:
            raise ValueError("only factual evidence can seed a hypothesis")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise ValueError("hypothesis_id is required")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("hypothesis statement is required")
        return LearningHypothesis(
            hypothesis_id=hypothesis_id.strip(),
            evidence_cycle_id=evidence.cycle_id,
            statement=statement.strip(),
            validated=False,
        )
