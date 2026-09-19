from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from datetime import datetime, timezone
import math

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
        self._lock = Lock()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "Requisição de execução inválida.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(
                accepted=False,
                message="PaperExecutor aceita somente modo DEMO.",
            )

        symbol = request.symbol.strip() if isinstance(request.symbol, str) else ""
        if not symbol or len(symbol) > 64:
            return ExecutionResult(False, "Símbolo inválido.")
        if not isinstance(request.amount, (int, float)) or isinstance(request.amount, bool) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return ExecutionResult(False, "Valor da execução deve ser positivo e finito.")
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0 or request.duration_seconds > 86_400:
            return ExecutionResult(False, "Duração deve ser positiva e válida.")
        if request.signal is None:
            return ExecutionResult(False, "Sinal de execução inválido.")

        with self._lock:
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
        with self._lock:
            return tuple(self._executions)
