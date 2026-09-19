from __future__ import annotations

import json
import math
import re
from datetime import datetime
from urllib.parse import quote, urlencode
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
    SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        self._timeout = float(timeout_seconds)

    def fetch(self, request: MarketDataRequest) -> list[Candle]:
        if not isinstance(request.symbol, str) or not self.SYMBOL_PATTERN.fullmatch(request.symbol.strip()):
            raise ValueError("invalid BiQuote symbol")
        if request.timeframe not in self.TIMEFRAMES:
            raise ValueError(f"unsupported BiQuote timeframe: {request.timeframe}")
        if isinstance(request.limit, bool) or not isinstance(request.limit, int) or request.limit <= 0 or request.limit > 1000:
            raise ValueError("invalid BiQuote limit")

        symbol = request.symbol.strip().upper()
        query = urlencode({"interval": request.timeframe, "limit": min(request.limit + 1, 1000)})
        url = f"{self.BASE_URL}/{quote(symbol, safe='')}/ohlc?{query}"
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
            timestamp = datetime.fromisoformat(str(bar["openTime"]).replace("Z", "+00:00"))
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
