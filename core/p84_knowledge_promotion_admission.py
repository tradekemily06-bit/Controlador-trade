from __future__ import annotations

from dataclasses import dataclass

from core.p83_validation_decision import ValidationDecision, ValidationDecisionStatus


@dataclass(frozen=True)
class KnowledgePromotionAdmission:
    admission_id: str
    decision_id: str
    result_id: str
    hypothesis_id: str
    status: str = "ADMITTED"
    real_execution_allowed: bool = False


class KnowledgePromotionAdmissionBoundary:
    def admit(self, decision: ValidationDecision | None, *, admission_id: str) -> KnowledgePromotionAdmission:
        if not isinstance(decision, ValidationDecision):
            raise ValueError("invalid validation decision")
        if decision.status is not ValidationDecisionStatus.VALIDATED:
            raise ValueError("only validated decisions can be admitted for promotion")
        if not isinstance(admission_id, str) or not admission_id.strip():
            raise ValueError("admission_id is required")
        return KnowledgePromotionAdmission(admission_id=admission_id.strip(), decision_id=decision.decision_id, result_id=decision.result_id, hypothesis_id=decision.hypothesis_id)
