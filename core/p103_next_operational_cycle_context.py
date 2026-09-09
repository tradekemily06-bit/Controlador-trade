from __future__ import annotations

from dataclasses import dataclass

from core.p102_next_operational_cycle_readiness import NextOperationalCycleReadiness


@dataclass(frozen=True)
class NextOperationalCycleContext:
    context_id: str
    readiness_id: str
    archive_id: str
    context: str
    real_execution_allowed: bool = False


class NextOperationalCycleContextBoundary:
    def create(
        self,
        readiness: NextOperationalCycleReadiness | None,
        *,
        context_id: str,
        context: str,
    ) -> NextOperationalCycleContext:
        if not isinstance(readiness, NextOperationalCycleReadiness):
            raise ValueError("invalid next operational cycle readiness")
        if readiness.status != "READY":
            raise ValueError("next operational cycle must be READY")
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("context_id is required")
        if not isinstance(context, str) or not context.strip():
            raise ValueError("context is required")
        return NextOperationalCycleContext(
            context_id=context_id.strip(),
            readiness_id=readiness.readiness_id,
            archive_id=readiness.archive_id,
            context=context.strip(),
        )
