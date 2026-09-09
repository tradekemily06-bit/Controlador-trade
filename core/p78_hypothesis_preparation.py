from __future__ import annotations

from dataclasses import dataclass

from core.p77_context_audit import ContextAudit, ContextAuditStatus


@dataclass(frozen=True)
class PreparedHypothesis:
    hypothesis_id: str
    context_id: str
    handoff_id: str
    statement: str
    validated: bool = False


class HypothesisPreparationBoundary:
    def prepare(
        self,
        audit: ContextAudit | None,
        *,
        hypothesis_id: str,
        statement: str,
    ) -> PreparedHypothesis:
        if not isinstance(audit, ContextAudit):
            raise ValueError("invalid context audit")
        if audit.status is not ContextAuditStatus.AUDITABLE:
            raise ValueError("context is not auditable")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise ValueError("hypothesis_id is required")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("hypothesis statement is required")
        return PreparedHypothesis(
            hypothesis_id=hypothesis_id.strip(),
            context_id=audit.context_id,
            handoff_id=audit.handoff_id,
            statement=statement.strip(),
            validated=False,
        )
