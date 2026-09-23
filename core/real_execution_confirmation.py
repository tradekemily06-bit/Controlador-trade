from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


@dataclass(frozen=True)
class ExecutionConfirmation:
    """Explicit user confirmation for one execution attempt."""

    confirmation_id: str
    request_id: str
    mode: ExecutionMode
    confirmed_at: datetime
    phrase: str

    def __post_init__(self) -> None:
        for name in ("confirmation_id", "request_id", "phrase"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("modo inválido.")
        if not isinstance(self.confirmed_at, datetime):
            raise ValueError("confirmed_at inválido.")
        if self.mode is ExecutionMode.REAL and self.phrase.strip().upper() != "CONFIRMO REAL":
            raise ValueError("confirmação REAL exige a frase exata: CONFIRMO REAL")


@dataclass(frozen=True)
class RealExecutionRequest:
    """REAL request that can only be created after explicit confirmation."""

    request_id: str
    symbol: str
    signal: Signal
    amount: float
    duration_seconds: int
    confirmation: ExecutionConfirmation

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id é obrigatório.")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol é obrigatório.")
        if not isinstance(self.signal, Signal) or self.signal is Signal.AGUARDAR:
            raise ValueError("signal REAL inválido.")
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool) or not math.isfinite(float(self.amount)) or self.amount <= 0:
            raise ValueError("amount inválido.")
        if not isinstance(self.duration_seconds, int) or isinstance(self.duration_seconds, bool) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds inválido.")
        if self.confirmation.mode is not ExecutionMode.REAL:
            raise ValueError("confirmação não é REAL.")
        if self.confirmation.request_id != self.request_id:
            raise ValueError("confirmation/request_id não correspondem.")

    def as_execution_request(self) -> ExecutionRequest:
        return ExecutionRequest(
            symbol=self.symbol,
            signal=self.signal,
            amount=float(self.amount),
            duration_seconds=self.duration_seconds,
            mode=ExecutionMode.REAL,
            request_id=self.request_id,
        )


def new_real_confirmation(*, confirmation_id: str, request_id: str, phrase: str) -> ExecutionConfirmation:
    return ExecutionConfirmation(
        confirmation_id=confirmation_id,
        request_id=request_id,
        mode=ExecutionMode.REAL,
        confirmed_at=datetime.now(timezone.utc),
        phrase=phrase,
    )
