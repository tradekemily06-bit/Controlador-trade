from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from core.models import Signal


class ExecutionMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


class ExecutionAction(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    signal: Signal
    amount: float
    duration_seconds: int
    mode: ExecutionMode
    request_id: str | None = None
    action: ExecutionAction = ExecutionAction.OPEN
    position_id: int | None = None


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    message: str
    external_id: str | None = None
    uncertain: bool = False


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
    """Provider-neutral identity of an external connection path.

    Broker, platform, adapter implementation and transport are independent
    dimensions. The core does not own a finite list of any of them.
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
