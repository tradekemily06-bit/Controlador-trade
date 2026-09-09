from __future__ import annotations

from dataclasses import dataclass

from core.p88_controlled_use_authorization import ControlledUseAuthorization
from core.p89_knowledge_governance_closure import KnowledgeGovernanceClosure


@dataclass(frozen=True)
class ControlledKnowledgeUse:
    use_id: str
    authorization_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    purpose: str
    status: str = "REQUESTED"
    real_execution_allowed: bool = False


class ControlledKnowledgeUseBoundary:
    def request(self, authorization: ControlledUseAuthorization | None, closure: KnowledgeGovernanceClosure | None, *, use_id: str, purpose: str) -> ControlledKnowledgeUse:
        if not isinstance(authorization, ControlledUseAuthorization) or not isinstance(closure, KnowledgeGovernanceClosure):
            raise ValueError("invalid governance artifacts")
        if authorization.status != "AUTHORIZED" or closure.status != "CLOSED":
            raise ValueError("governance artifacts are not eligible")
        if closure.authorization_id != authorization.authorization_id:
            raise ValueError("authorization provenance mismatch")
        if not isinstance(use_id, str) or not use_id.strip() or not isinstance(purpose, str) or not purpose.strip():
            raise ValueError("use_id and purpose are required")
        return ControlledKnowledgeUse(use_id=use_id.strip(), authorization_id=authorization.authorization_id, knowledge_id=authorization.knowledge_id, hypothesis_id=authorization.hypothesis_id, scope=authorization.scope, purpose=purpose.strip())
