from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
import math

from core.models import Signal


class ExecutionMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    signal: Signal
    amount: float
    duration_seconds: int
    mode: ExecutionMode
    request_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol.strip():
            raise ValueError("symbol é obrigatório.")
        if not isinstance(self.signal, Signal):
            raise ValueError("signal inválido.")
        if not isinstance(self.amount, (int, float)) or isinstance(self.amount, bool) or not math.isfinite(float(self.amount)) or self.amount <= 0:
            raise ValueError("amount deve ser um número finito positivo.")
        if type(self.duration_seconds) is not int or self.duration_seconds <= 0:
            raise ValueError("duration_seconds deve ser um inteiro positivo.")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode inválido.")
        if self.request_id is not None and (
            type(self.request_id) is not str or not self.request_id.strip() or self.request_id != self.request_id.strip()
        ):
            raise ValueError("request_id inválido ou não canônico.")


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    message: str
    external_id: str | None = None


class ExecutionPort(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class BrokerAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def is_available(self) -> bool:
        ...
