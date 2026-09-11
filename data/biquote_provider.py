from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data.feed import MarketDataProvider, MarketDataRequest
from data.models import Candle


class BiQuoteProvider(MarketDataProvider):
    """Read-only BiQuote OHLC provider.

    Public read endpoints require no API key. Only closed bars are exposed to
    the core so an open candle cannot be treated as confirmed market data.
    """

    BASE_URL = "https://biquote.io/api"
    TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout = timeout_seconds

    def fetch(self, request: MarketDataRequest) -> list[Candle]:
        if request.timeframe not in self.TIMEFRAMES:
            raise ValueError(f"unsupported BiQuote timeframe: {request.timeframe}")

        query = urlencode(
            {"interval": request.timeframe, "limit": min(request.limit + 1, 1000)}
        )
        url = f"{self.BASE_URL}/{request.symbol.upper()}/ohlc?{query}"
        http_request = Request(url, headers={"Accept": "application/json"})
        with urlopen(http_request, timeout=self._timeout) as response:
            payload = json.load(response)

        bars = payload.get("bars")
        if not isinstance(bars, list):
            raise ValueError("BiQuote response missing bars")

        candles: list[Candle] = []
        for bar in bars:
            if not isinstance(bar, dict) or bar.get("isOpen") is True:
                continue
            timestamp = datetime.fromisoformat(
                str(bar["openTime"]).replace("Z", "+00:00")
            )
            candles.append(
                Candle(
                    timestamp=timestamp,
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar.get("tickVolume", bar.get("volume", 0)) or 0),
                )
            )

        candles.reverse()
        return candles[-request.limit :]
