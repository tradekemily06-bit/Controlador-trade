from __future__ import annotations

from dataclasses import dataclass

from core.p104_operational_hypothesis_preparation import OperationalHypothesisPreparation


@dataclass(frozen=True)
class OperationalHypothesisAdmission:
    admission_id: str
    hypothesis_id: str
    context_id: str
    readiness_id: str
    status: str = "ADMITTED"
    real_execution_allowed: bool = False


class OperationalHypothesisAdmissionBoundary:
    def admit(
        self,
        hypothesis: OperationalHypothesisPreparation | None,
        *,
        admission_id: str,
    ) -> OperationalHypothesisAdmission:
        if not isinstance(hypothesis, OperationalHypothesisPreparation):
            raise ValueError("invalid operational hypothesis")
        if hypothesis.validated:
            raise ValueError("P104 hypothesis must remain unvalidated")
        if not isinstance(admission_id, str) or not admission_id.strip():
            raise ValueError("admission_id is required")
        return OperationalHypothesisAdmission(
            admission_id=admission_id.strip(),
            hypothesis_id=hypothesis.hypothesis_id,
            context_id=hypothesis.context_id,
            readiness_id=hypothesis.readiness_id,
        )
