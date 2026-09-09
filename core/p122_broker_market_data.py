from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from data.models import Candle
from data.normalizer import normalize_candle
from data.validator import validate_candles


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

        raw = tuple(self._provider.fetch_market_data(request))
        if not raw:
            raise ValueError("provider não retornou candles")

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
            raise ValueError("provider retornou sequência de candles inválida")

        if len(normalized) > request.limit:
            normalized = normalized[-request.limit:]

        return BrokerMarketDataSnapshot(
            symbol=request.symbol.strip(),
            timeframe=request.timeframe.strip(),
            candles=normalized,
            source=self._source,
            received_at=received_at or datetime.now().astimezone(),
        )
