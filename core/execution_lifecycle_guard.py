from __future__ import annotations

from dataclasses import dataclass

from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState


@dataclass(frozen=True)
class LifecycleTransition:
    allowed: bool
    reason: str


class ExecutionLifecycleGuard:
    """Read-only transition policy; it never persists or executes an operation."""

    def validate(self, current: ExecutionLifecycleRecord | None, target: ExecutionLifecycleState) -> LifecycleTransition:
        if not isinstance(target, ExecutionLifecycleState):
            return LifecycleTransition(False, "estado de destino inválido")
        if current is None:
            if target is ExecutionLifecycleState.PENDING:
                return LifecycleTransition(True, "novo ciclo pode iniciar em PENDING")
            return LifecycleTransition(False, "novo ciclo deve iniciar em PENDING")
        if not isinstance(current, ExecutionLifecycleRecord):
            return LifecycleTransition(False, "estado atual inválido")
        allowed = {
            ExecutionLifecycleState.PENDING: {
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            },
            ExecutionLifecycleState.UNKNOWN: set(),
            ExecutionLifecycleState.ACCEPTED: set(),
            ExecutionLifecycleState.REJECTED: set(),
        }
        if target in allowed.get(current.state, set()):
            return LifecycleTransition(True, "transição permitida")
        if current.state is ExecutionLifecycleState.UNKNOWN:
            return LifecycleTransition(False, "UNKNOWN exige reconciliação explícita")
        return LifecycleTransition(False, "transição inválida")
