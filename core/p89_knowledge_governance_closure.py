from __future__ import annotations

from dataclasses import dataclass

from core.p88_controlled_use_authorization import ControlledUseAuthorization


@dataclass(frozen=True)
class KnowledgeGovernanceClosure:
    closure_id: str
    authorization_id: str
    interpretation_id: str
    audit_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    status: str = "CLOSED"
    real_execution_allowed: bool = False


class KnowledgeGovernanceClosureBoundary:
    def close(self, authorization: ControlledUseAuthorization | None, *, closure_id: str) -> KnowledgeGovernanceClosure:
        if not isinstance(authorization, ControlledUseAuthorization):
            raise ValueError("invalid controlled use authorization")
        if authorization.status != "AUTHORIZED":
            raise ValueError("authorization is not active")
        if not isinstance(closure_id, str) or not closure_id.strip():
            raise ValueError("closure_id is required")
        return KnowledgeGovernanceClosure(closure_id=closure_id.strip(), authorization_id=authorization.authorization_id, interpretation_id=authorization.interpretation_id, audit_id=authorization.audit_id, knowledge_id=authorization.knowledge_id, hypothesis_id=authorization.hypothesis_id, scope=authorization.scope)
