from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .models import Signal


class APIEnvironment(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


class APIStatus(str, Enum):
    OK = "OK"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    timeframe: str
    limit: int = 50

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError("limit must be a positive integer")


@dataclass(frozen=True)
class AnalysisRequest:
    symbol: str
    timeframe: str = "5m"
    candle_limit: int = 50
    environment: APIEnvironment = APIEnvironment.DEMO

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if isinstance(self.candle_limit, bool) or not isinstance(self.candle_limit, int) or self.candle_limit <= 0:
            raise ValueError("candle_limit must be a positive integer")
        if not isinstance(self.environment, APIEnvironment):
            raise ValueError("environment must be an APIEnvironment")


@dataclass(frozen=True)
class SignalResponse:
    status: APIStatus
    signal: Signal
    score: float
    reason: str
    confirmed: bool
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    environment: APIEnvironment = APIEnvironment.DEMO

    @classmethod
    def blocked(cls, *, reason: str, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> "SignalResponse":
        return cls(
            status=APIStatus.BLOCKED,
            signal=Signal.AGUARDAR,
            score=0.0,
            reason=reason,
            confirmed=False,
            symbol=symbol,
            timeframe=timeframe,
            environment=APIEnvironment.REAL,
        )


@dataclass(frozen=True)
class HealthResponse:
    status: APIStatus
    environment: APIEnvironment
    broker_connected: bool
    message: str


@dataclass(frozen=True)
class AuditEvent:
    event: str
    status: APIStatus
    environment: APIEnvironment
    symbol: Optional[str] = None
    detail: str = ""
