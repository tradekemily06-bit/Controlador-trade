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


class ExecutionPort(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class BrokerAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def is_available(self) -> bool:
        ...


@dataclass(frozen=True)
class AdapterConnectionIdentity:
    """Provider-neutral identity of the external connection path.

    A broker, trading platform, adapter implementation and transport are
    separate dimensions. None of them is a finite list owned by the core.
    """

    broker_id: str
    platform_id: str
    adapter_id: str
    transport_id: str

    def __post_init__(self) -> None:
        for name in ("broker_id", "platform_id", "adapter_id", "transport_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
