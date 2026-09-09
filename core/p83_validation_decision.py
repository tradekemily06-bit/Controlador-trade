from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p82_validation_result import ValidationResult, ValidationResultStatus


class ValidationDecisionStatus(str, Enum):
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ValidationDecision:
    decision_id: str
    result_id: str
    test_id: str
    hypothesis_id: str
    status: ValidationDecisionStatus
    rationale: str


class ValidationDecisionBoundary:
    def decide(self, result: ValidationResult | None, *, decision_id: str, status: ValidationDecisionStatus, rationale: str) -> ValidationDecision:
        if not isinstance(result, ValidationResult):
            raise ValueError("invalid validation result")
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id is required")
        if not isinstance(status, ValidationDecisionStatus):
            raise ValueError("invalid validation decision status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        if status is ValidationDecisionStatus.VALIDATED and result.status is not ValidationResultStatus.POSITIVE:
            raise ValueError("only positive results can be validated")
        if status is ValidationDecisionStatus.REJECTED and result.status is not ValidationResultStatus.NEGATIVE:
            raise ValueError("only negative results can be rejected")
        if status is ValidationDecisionStatus.INCONCLUSIVE and result.status is not ValidationResultStatus.INCONCLUSIVE:
            raise ValueError("inconclusive decision requires inconclusive result")
        return ValidationDecision(decision_id=decision_id.strip(), result_id=result.result_id, test_id=result.test_id, hypothesis_id=result.hypothesis_id, status=status, rationale=rationale.strip())
