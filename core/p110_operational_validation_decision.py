from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from core.p109_operational_validation_result import OperationalValidationResult

DecisionStatus = Literal["VALIDATED", "REJECTED", "INCONCLUSIVE"]

@dataclass(frozen=True)
class OperationalValidationDecision:
    decision_id: str
    result_id: str
    run_id: str
    specification_id: str
    audit_id: str
    hypothesis_id: str
    status: DecisionStatus
    rationale: str
    real_execution_allowed: bool = False

class OperationalValidationDecisionBoundary:
    def decide(self, result: OperationalValidationResult | None, *, decision_id: str, status: DecisionStatus, rationale: str) -> OperationalValidationDecision:
        if not isinstance(result, OperationalValidationResult): raise ValueError("invalid validation result")
        expected = {"POSITIVE":"VALIDATED", "NEGATIVE":"REJECTED", "INCONCLUSIVE":"INCONCLUSIVE"}[result.status]
        if status != expected: raise ValueError("decision status does not match validation result")
        if not isinstance(decision_id, str) or not decision_id.strip() or not isinstance(rationale, str) or not rationale.strip(): raise ValueError("decision_id and rationale are required")
        return OperationalValidationDecision(decision_id.strip(), result.result_id, result.run_id, result.specification_id, result.audit_id, result.hypothesis_id, status, rationale.strip())
