from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from data.models import Candle
from data.normalizer import normalize_candle
from data.validator import validate_candles
from data.timeframes import normalize_timeframe


@dataclass(frozen=True)
class BrokerMarketDataRequest:
    symbol: str
    timeframe: str
    limit: int

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol inválido")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe inválido")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit <= 0:
            raise ValueError("limit inválido")


@dataclass(frozen=True)
class BrokerMarketDataSnapshot:
    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]
    source: str
    received_at: datetime


class BrokerMarketDataPort(Protocol):
    """Broker-specific adapters implement this read-only market-data contract."""

    def fetch_market_data(self, request: BrokerMarketDataRequest) -> Sequence[Candle]:
        ...


class BrokerMarketDataBoundary:
    """Normalizes and validates broker data before it enters the trading core."""

    def __init__(self, provider: BrokerMarketDataPort, source: str) -> None:
        if provider is None:
            raise ValueError("provider obrigatório")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source inválida")
        self._provider = provider
        self._source = source.strip()

    def fetch(
        self,
        request: BrokerMarketDataRequest,
        received_at: datetime | None = None,
    ) -> BrokerMarketDataSnapshot:
        if not isinstance(request, BrokerMarketDataRequest):
            raise TypeError("request deve ser BrokerMarketDataRequest")

        canonical_timeframe = normalize_timeframe(request.timeframe)
        canonical_request = BrokerMarketDataRequest(
            symbol=request.symbol.strip().upper(),
            timeframe=canonical_timeframe,
            limit=request.limit,
        )
        raw_result = self._provider.fetch_market_data(canonical_request)
        if raw_result is None:
            raise ValueError("provider retornou None")
        raw = tuple(raw_result)
        if not raw:
            raise ValueError("provider não retornou candles")

        normalized_items = []
        for candle in raw:
            if not isinstance(candle, Candle):
                raise ValueError("provider retornou candle de tipo inválido")
            if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
                raise ValueError("provider retornou timestamp sem fuso horário")
            values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if any(isinstance(value, (bool, str, bytes)) for value in values):
                raise ValueError("provider retornou campo numérico inválido")
            normalized_items.append(normalize_candle(
                timestamp=candle.timestamp.astimezone(timezone.utc),
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            ))
        normalized = tuple(normalized_items)
        if not validate_candles(list(normalized)):
            raise ValueError("provider retornou sequência de candles inválida")

        if len(normalized) > request.limit:
            normalized = normalized[-request.limit:]

        return BrokerMarketDataSnapshot(
            symbol=request.symbol.strip(),
            timeframe=canonical_timeframe,
            candles=normalized,
            source=self._source,
            received_at=received_at or datetime.now().astimezone(),
        )
