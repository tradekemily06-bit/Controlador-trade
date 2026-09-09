from __future__ import annotations
from dataclasses import dataclass
from core.p107_operational_validation_specification import OperationalValidationSpecification

@dataclass(frozen=True)
class OperationalValidationRun:
    run_id: str
    specification_id: str
    audit_id: str
    hypothesis_id: str
    sample_size: int
    observation: str
    real_execution_allowed: bool = False

class OperationalValidationRunBoundary:
    def record(self, specification: OperationalValidationSpecification | None, *, run_id: str, sample_size: int, observation: str) -> OperationalValidationRun:
        if not isinstance(specification, OperationalValidationSpecification): raise ValueError("invalid validation specification")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0: raise ValueError("sample_size must be positive")
        if not isinstance(run_id, str) or not run_id.strip() or not isinstance(observation, str) or not observation.strip(): raise ValueError("run_id and observation are required")
        return OperationalValidationRun(run_id.strip(), specification.specification_id, specification.audit_id, specification.hypothesis_id, sample_size, observation.strip())
