from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from core.p108_operational_validation_run import OperationalValidationRun

ValidationResultStatus = Literal["POSITIVE", "NEGATIVE", "INCONCLUSIVE"]

@dataclass(frozen=True)
class OperationalValidationResult:
    result_id: str
    run_id: str
    specification_id: str
    audit_id: str
    hypothesis_id: str
    status: ValidationResultStatus
    rationale: str
    real_execution_allowed: bool = False

class OperationalValidationResultBoundary:
    def conclude(self, run: OperationalValidationRun | None, *, result_id: str, status: ValidationResultStatus, rationale: str) -> OperationalValidationResult:
        if not isinstance(run, OperationalValidationRun): raise ValueError("invalid validation run")
        if status not in ("POSITIVE", "NEGATIVE", "INCONCLUSIVE"): raise ValueError("invalid validation result status")
        if not isinstance(result_id, str) or not result_id.strip() or not isinstance(rationale, str) or not rationale.strip(): raise ValueError("result_id and rationale are required")
        return OperationalValidationResult(result_id.strip(), run.run_id, run.specification_id, run.audit_id, run.hypothesis_id, status, rationale.strip())
