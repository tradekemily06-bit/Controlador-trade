from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from data.models import Candle
from data.normalizer import normalize_candle
from data.validator import validate_candles
from data.timeframes import get_timeframe_interval


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

    def fetch(
        self,
        request: MarketDataRequest,
        received_at: datetime | None = None,
        *,
        live_candle: Candle | None = None,
    ) -> MarketDataResult:
        if not isinstance(request, MarketDataRequest):
            raise TypeError("request must be MarketDataRequest")
        raw = tuple(self._provider.fetch(request))
        if not raw:
            raise ValueError("provider returned no candles")
        normalized = tuple(
            normalize_candle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in raw
        )
        if not validate_candles(list(normalized)):
            raise ValueError("provider returned invalid candle sequence")
        if live_candle is not None:
            if not isinstance(live_candle, Candle):
                raise TypeError("live_candle must be a validated Candle")
            if live_candle.timestamp.tzinfo is None:
                raise ValueError("live candle timestamp must be timezone-aware")
            overlay = normalize_candle(
                timestamp=live_candle.timestamp,
                open=live_candle.open,
                high=live_candle.high,
                low=live_candle.low,
                close=live_candle.close,
                volume=live_candle.volume,
            )
            last_at = normalized[-1].timestamp
            if last_at.tzinfo is None:
                raise ValueError("provider candle timestamp must be timezone-aware")
            delta = overlay.timestamp.astimezone(timezone.utc) - last_at.astimezone(timezone.utc)
            if delta.total_seconds() == 0:
                normalized = (*normalized[:-1], overlay)
            elif delta == get_timeframe_interval(request.timeframe):
                normalized = (*normalized, overlay)
            else:
                raise ValueError("live candle is not contiguous with the validated provider history")
            if not validate_candles(list(normalized)):
                raise ValueError("live candle overlay produced an invalid sequence")
        if len(normalized) > request.limit:
            normalized = normalized[-request.limit:]
        return MarketDataResult(
            candles=normalized,
            source=self._source,
            received_at=received_at or datetime.now().astimezone(),
        )
