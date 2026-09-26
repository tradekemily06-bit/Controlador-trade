from __future__ import annotations

from typing import Any

from core.p122_broker_market_data import BrokerMarketDataRequest
from data.feed import MarketDataProvider, MarketDataRequest
from data.models import Candle
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter


class ICMarketsMT5DemoRuntimeProvider(MarketDataProvider):
    """Adapts the read-only MT5 DEMO market source to the core MarketDataFeed."""

    def __init__(self, *, mt5_module: Any = None) -> None:
        self._adapter = ICMarketsMT5DemoMarketDataAdapter(mt5_module=mt5_module)

    def fetch(self, request: MarketDataRequest) -> tuple[Candle, ...]:
        if not isinstance(request, MarketDataRequest):
            raise TypeError("request deve ser MarketDataRequest")
        return self._adapter.fetch_market_data(
            BrokerMarketDataRequest(
                symbol=request.symbol,
                timeframe=request.timeframe,
                limit=request.limit,
            )
        )


def build_mt5_demo_runtime_feed(*, mt5_module: Any = None):
    """Build the validated core feed backed by MT5 DEMO completed candles."""
    from data.feed import MarketDataFeed

    return MarketDataFeed(
        ICMarketsMT5DemoRuntimeProvider(mt5_module=mt5_module),
        source="IC Markets MT5 DEMO",
    )
