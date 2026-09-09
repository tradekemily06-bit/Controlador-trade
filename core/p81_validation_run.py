from __future__ import annotations

from dataclasses import dataclass

from core.p80_validation_specification import ValidationSpecification


@dataclass(frozen=True)
class ValidationRun:
    run_id: str
    test_id: str
    admission_id: str
    hypothesis_id: str
    sample_size: int
    observation: str
    real_execution_allowed: bool = False


class ValidationRunBoundary:
    def record(self, specification: ValidationSpecification | None, *, run_id: str, sample_size: int, observation: str) -> ValidationRun:
        if not isinstance(specification, ValidationSpecification):
            raise ValueError("invalid validation specification")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id is required")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("observation is required")
        return ValidationRun(run_id=run_id.strip(), test_id=specification.test_id, admission_id=specification.admission_id, hypothesis_id=specification.hypothesis_id, sample_size=sample_size, observation=observation.strip())
