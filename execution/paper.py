from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from execution.ports import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
)


@dataclass(frozen=True)
class PaperExecution:
    request: ExecutionRequest
    result: ExecutionResult
    timestamp: datetime


class PaperExecutor:
    """Executa ordens somente em ambiente simulado."""

    def __init__(self) -> None:
        self._executions: list[PaperExecution] = []
        self._next_id = 1

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(
                accepted=False,
                message="PaperExecutor aceita somente modo DEMO.",
            )

        if not request.symbol.strip():
            return ExecutionResult(
                accepted=False,
                message="Símbolo não pode ser vazio.",
            )

        if request.amount <= 0:
            return ExecutionResult(
                accepted=False,
                message="Valor da execução deve ser positivo.",
            )

        if request.duration_seconds <= 0:
            return ExecutionResult(
                accepted=False,
                message="Duração deve ser positiva.",
            )

        external_id = f"PAPER-{self._next_id:06d}"
        self._next_id += 1

        result = ExecutionResult(
            accepted=True,
            message="Execução DEMO registrada.",
            external_id=external_id,
        )

        self._executions.append(
            PaperExecution(
                request=request,
                result=result,
                timestamp=datetime.now(timezone.utc),
            )
        )

        return result

    def executions(self) -> tuple[PaperExecution, ...]:
        return tuple(self._executions)
