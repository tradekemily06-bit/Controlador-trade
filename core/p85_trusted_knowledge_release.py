from __future__ import annotations

from dataclasses import dataclass

from core.p84_knowledge_promotion_admission import KnowledgePromotionAdmission


@dataclass(frozen=True)
class TrustedKnowledgeRelease:
    knowledge_id: str
    promotion_admission_id: str
    decision_id: str
    result_id: str
    hypothesis_id: str
    statement: str
    release_status: str = "RELEASED"
    real_execution_allowed: bool = False


class TrustedKnowledgeReleaseBoundary:
    def release(self, admission: KnowledgePromotionAdmission | None, *, knowledge_id: str, statement: str) -> TrustedKnowledgeRelease:
        if not isinstance(admission, KnowledgePromotionAdmission):
            raise ValueError("invalid knowledge promotion admission")
        if admission.status != "ADMITTED":
            raise ValueError("promotion admission is not active")
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            raise ValueError("knowledge_id is required")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("knowledge statement is required")
        return TrustedKnowledgeRelease(knowledge_id=knowledge_id.strip(), promotion_admission_id=admission.admission_id, decision_id=admission.decision_id, result_id=admission.result_id, hypothesis_id=admission.hypothesis_id, statement=statement.strip())
