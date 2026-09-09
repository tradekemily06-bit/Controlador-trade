from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from data.models import Candle
from data.normalizer import normalize_candles
from data.validator import validate_candles


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    timeframe: str
    limit: int

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit <= 0:
            raise ValueError("limit must be a positive integer")


@dataclass(frozen=True)
class MarketDataResult:
    candles: tuple[Candle, ...]
    source: str
    received_at: datetime


class MarketDataProvider(Protocol):
    def fetch(self, request: MarketDataRequest) -> Sequence[Candle]:
        ...


class MarketDataFeed:
    """Safe boundary that normalizes and validates provider data before the core sees it."""

    def __init__(self, provider: MarketDataProvider, source: str = "unknown") -> None:
        if provider is None:
            raise ValueError("provider is required")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be non-empty")
        self._provider = provider
        self._source = source.strip()

    def fetch(self, request: MarketDataRequest, received_at: datetime | None = None) -> MarketDataResult:
        if not isinstance(request, MarketDataRequest):
            raise TypeError("request must be MarketDataRequest")
        raw = self._provider.fetch(request)
        candles = tuple(raw)
        if not candles:
            raise ValueError("provider returned no candles")
        normalized = tuple(normalize_candles(candles))
        validate_candles(normalized)
        if len(normalized) > request.limit:
            normalized = normalized[-request.limit:]
        return MarketDataResult(
            candles=normalized,
            source=self._source,
            received_at=received_at or datetime.now().astimezone(),
        )
