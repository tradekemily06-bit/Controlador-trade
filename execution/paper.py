from __future__ import annotations

from dataclasses import dataclass
import math

from core.models import Signal
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
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "requisição de execução inválida.")
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return ExecutionResult(False, "AGUARDAR não pode gerar ordem.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(
                accepted=False,
                message="PaperExecutor aceita somente modo DEMO.",
            )
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(
                accepted=False,
                message="request_id obrigatório para execução DEMO.",
            )

        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return ExecutionResult(
                accepted=False,
                message="Símbolo não pode ser vazio.",
            )

        if isinstance(request.amount, bool) or not isinstance(request.amount, (int, float)) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return ExecutionResult(
                accepted=False,
                message="Valor da execução deve ser positivo.",
            )

        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
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
