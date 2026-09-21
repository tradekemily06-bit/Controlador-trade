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
    uncertain: bool = False
    external_id_kind: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool) or not isinstance(self.uncertain, bool):
            raise ValueError("accepted/uncertain devem ser booleanos.")
        if self.accepted and self.uncertain:
            raise ValueError("resultado não pode ser aceito e incerto simultaneamente.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message é obrigatório.")
        if self.external_id is not None and (not isinstance(self.external_id, str) or not self.external_id.strip()):
            raise ValueError("external_id inválido.")
        if self.external_id_kind is not None and self.external_id_kind not in {"ORDER", "DEAL", "POSITION", "EXECUTION"}:
            raise ValueError("external_id_kind inválido.")
        if self.external_id is None and self.external_id_kind is not None:
            raise ValueError("external_id_kind exige external_id.")


class ExecutionPort(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class BrokerAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def is_available(self) -> bool:
        ...
