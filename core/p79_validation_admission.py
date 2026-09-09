from __future__ import annotations

from dataclasses import dataclass

from core.p78_hypothesis_preparation import PreparedHypothesis


@dataclass(frozen=True)
class ValidationAdmission:
    admission_id: str
    hypothesis_id: str
    context_id: str
    handoff_id: str
    statement: str
    status: str = "ADMITTED"
    real_execution_allowed: bool = False


class ValidationAdmissionBoundary:
    def admit(
        self,
        hypothesis: PreparedHypothesis | None,
        *,
        admission_id: str,
    ) -> ValidationAdmission:
        if not isinstance(hypothesis, PreparedHypothesis):
            raise ValueError("invalid prepared hypothesis")
        if hypothesis.validated:
            raise ValueError("validated hypotheses cannot be re-admitted")
        if not isinstance(admission_id, str) or not admission_id.strip():
            raise ValueError("admission_id is required")
        return ValidationAdmission(
            admission_id=admission_id.strip(),
            hypothesis_id=hypothesis.hypothesis_id,
            context_id=hypothesis.context_id,
            handoff_id=hypothesis.handoff_id,
            statement=hypothesis.statement,
        )
