from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p76_cycle_context import NextCycleContext


class ContextAuditStatus(str, Enum):
    AUDITABLE = "AUDITABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ContextAudit:
    context_id: str
    handoff_id: str
    archive_id: str
    status: ContextAuditStatus
    rationale: str


class ContextAuditBoundary:
    def audit(
        self,
        context: NextCycleContext | None,
        *,
        status: ContextAuditStatus,
        rationale: str,
    ) -> ContextAudit:
        if not isinstance(context, NextCycleContext):
            raise ValueError("invalid next-cycle context")
        if not isinstance(status, ContextAuditStatus):
            raise ValueError("invalid context audit status")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("context audit rationale is required")
        values = (context.context_id, context.handoff_id, context.archive_id, context.context)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("incomplete context")
        return ContextAudit(
            context_id=context.context_id,
            handoff_id=context.handoff_id,
            archive_id=context.archive_id,
            status=status,
            rationale=rationale.strip(),
        )
