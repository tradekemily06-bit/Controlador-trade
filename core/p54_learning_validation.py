from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p53_learning_hypothesis import LearningHypothesis


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class LearningValidation:
    hypothesis_id: str
    test_id: str
    status: ValidationStatus
    sample_size: int
    observation: str


class LearningValidationBoundary:
    """Records explicit validation observations; it never runs tests or promotes knowledge."""

    def validate(
        self,
        hypothesis: LearningHypothesis | None,
        *,
        test_id: str,
        status: ValidationStatus,
        sample_size: int,
        observation: str,
    ) -> LearningValidation:
        if not isinstance(hypothesis, LearningHypothesis):
            raise ValueError("invalid learning hypothesis")
        if hypothesis.validated:
            raise ValueError("hypothesis validation state must remain false at P54")
        if not isinstance(test_id, str) or not test_id.strip():
            raise ValueError("test_id is required")
        if not isinstance(status, ValidationStatus):
            raise ValueError("invalid validation status")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("validation observation is required")
        return LearningValidation(
            hypothesis_id=hypothesis.hypothesis_id,
            test_id=test_id.strip(),
            status=status,
            sample_size=sample_size,
            observation=observation.strip(),
        )
