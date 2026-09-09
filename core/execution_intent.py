from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


@dataclass(frozen=True)
class ExecutionIntent:
    """Validated, immutable request boundary; creating it never executes anything."""

    request_id: str
    symbol: str
    signal: Signal
    amount: float
    duration_seconds: int
    mode: ExecutionMode
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id é obrigatório.")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol é obrigatório.")
        if not isinstance(self.signal, Signal):
            raise ValueError("signal inválido.")
        if self.signal is Signal.AGUARDAR:
            raise ValueError("AGUARDAR não pode gerar intenção de execução.")
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool) or not math.isfinite(float(self.amount)) or self.amount <= 0:
            raise ValueError("amount deve ser um número finito positivo.")
        if not isinstance(self.duration_seconds, int) or isinstance(self.duration_seconds, bool) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds deve ser um inteiro positivo.")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("modo de execução inválido.")
        if self.mode is ExecutionMode.REAL:
            raise ValueError("execução REAL permanece bloqueada nesta etapa.")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at inválido.")

    def as_execution_request(self) -> ExecutionRequest:
        """Build the existing port DTO without invoking any execution adapter."""
        return ExecutionRequest(
            symbol=self.symbol,
            signal=self.signal,
            amount=self.amount,
            duration_seconds=self.duration_seconds,
            mode=self.mode,
        )
