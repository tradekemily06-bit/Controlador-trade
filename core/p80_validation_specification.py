from __future__ import annotations

from dataclasses import dataclass

from core.p79_validation_admission import ValidationAdmission


@dataclass(frozen=True)
class ValidationSpecification:
    test_id: str
    admission_id: str
    hypothesis_id: str
    statement: str
    environment: str
    criteria: str
    real_execution_allowed: bool = False


class ValidationSpecificationBoundary:
    def specify(self, admission: ValidationAdmission | None, *, test_id: str, environment: str, criteria: str) -> ValidationSpecification:
        if not isinstance(admission, ValidationAdmission):
            raise ValueError("invalid validation admission")
        if admission.status != "ADMITTED":
            raise ValueError("validation admission is not active")
        values = (test_id, environment, criteria)
        if not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError("test_id, environment and criteria are required")
        return ValidationSpecification(test_id=test_id.strip(), admission_id=admission.admission_id, hypothesis_id=admission.hypothesis_id, statement=admission.statement, environment=environment.strip(), criteria=criteria.strip())
