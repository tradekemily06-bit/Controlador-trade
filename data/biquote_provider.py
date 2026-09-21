from __future__ import annotations

import http.client
import json
import re
from datetime import datetime
from urllib.parse import quote, urlencode

from data.feed import MarketDataProvider, MarketDataRequest
from data.models import Candle


class BiQuoteProvider(MarketDataProvider):
    """Read-only BiQuote OHLC provider.

    Public read endpoints require no API key. Only closed bars are exposed to
    the core so an open candle cannot be treated as confirmed market data.
    """

    HOST = "biquote.io"
    BASE_PATH = "/api"
    TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
    _SYMBOL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout = timeout_seconds

    def fetch(self, request: MarketDataRequest) -> list[Candle]:
        if request.timeframe not in self.TIMEFRAMES:
            raise ValueError(f"unsupported BiQuote timeframe: {request.timeframe}")
        symbol = request.symbol.strip().upper()
        if not self._SYMBOL_RE.fullmatch(symbol):
            raise ValueError("invalid BiQuote symbol")

        query = urlencode(
            {"interval": request.timeframe, "limit": min(request.limit + 1, 1000)}
        )
        path = f"{self.BASE_PATH}/{quote(symbol, safe='._-')}/ohlc?{query}"

        connection = http.client.HTTPSConnection(self.HOST, timeout=self._timeout)
        try:
            connection.request("GET", path, headers={"Accept": "application/json"})
            response = connection.getresponse()
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"BiQuote HTTP status {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

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
