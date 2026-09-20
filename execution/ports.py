from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

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


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    message: str
    external_id: str | None = None
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ValueError("accepted inválido.")
        if not isinstance(self.ambiguous, bool):
            raise ValueError("ambiguous inválido.")
        if self.accepted and self.ambiguous:
            raise ValueError("resultado não pode ser simultaneamente aceito e ambíguo.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message inválida.")
        if self.external_id is not None and (
            not isinstance(self.external_id, str) or not self.external_id.strip()
        ):
            raise ValueError("external_id inválido.")


class ExecutionPort(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class BrokerAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def is_available(self) -> bool:
        ...
