from __future__ import annotations

from dataclasses import dataclass

from core.p103_next_operational_cycle_context import NextOperationalCycleContext


@dataclass(frozen=True)
class OperationalHypothesisPreparation:
    hypothesis_id: str
    context_id: str
    readiness_id: str
    statement: str
    validated: bool = False
    real_execution_allowed: bool = False


class OperationalHypothesisPreparationBoundary:
    def prepare(
        self,
        context: NextOperationalCycleContext | None,
        *,
        hypothesis_id: str,
        statement: str,
    ) -> OperationalHypothesisPreparation:
        if not isinstance(context, NextOperationalCycleContext):
            raise ValueError("invalid next operational cycle context")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise ValueError("hypothesis_id is required")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("statement is required")
        return OperationalHypothesisPreparation(
            hypothesis_id=hypothesis_id.strip(),
            context_id=context.context_id,
            readiness_id=context.readiness_id,
            statement=statement.strip(),
        )
