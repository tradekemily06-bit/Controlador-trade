from __future__ import annotations

from dataclasses import dataclass

from core.p87_controlled_knowledge_interpretation import ControlledKnowledgeInterpretation


@dataclass(frozen=True)
class ControlledUseAuthorization:
    authorization_id: str
    interpretation_id: str
    audit_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    status: str = "AUTHORIZED"
    real_execution_allowed: bool = False


class ControlledUseAuthorizationBoundary:
    def authorize(self, interpretation: ControlledKnowledgeInterpretation | None, *, authorization_id: str, scope: str) -> ControlledUseAuthorization:
        if not isinstance(interpretation, ControlledKnowledgeInterpretation):
            raise ValueError("invalid controlled knowledge interpretation")
        if not isinstance(authorization_id, str) or not authorization_id.strip() or not isinstance(scope, str) or not scope.strip():
            raise ValueError("authorization_id and scope are required")
        return ControlledUseAuthorization(authorization_id=authorization_id.strip(), interpretation_id=interpretation.interpretation_id, audit_id=interpretation.audit_id, knowledge_id=interpretation.knowledge_id, hypothesis_id=interpretation.hypothesis_id, scope=scope.strip())