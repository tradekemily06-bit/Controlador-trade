from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p81_validation_run import ValidationRun


class ValidationResultStatus(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ValidationResult:
    result_id: str
    run_id: str
    test_id: str
    hypothesis_id: str
    status: ValidationResultStatus
    rationale: str


class ValidationResultBoundary:
    def conclude(self, run: ValidationRun | None, *, result_id: str, status: ValidationResultStatus, rationale: str) -> ValidationResult:
        if not isinstance(run, ValidationRun):
            raise ValueError("invalid validation run")
        if not isinstance(result_id, str) or not result_id.strip():
            raise ValueError("result_id is required")
        if not isinstance(status, ValidationResultStatus):
            raise ValueError("invalid validation result status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        return ValidationResult(result_id=result_id.strip(), run_id=run.run_id, test_id=run.test_id, hypothesis_id=run.hypothesis_id, status=status, rationale=rationale.strip())
