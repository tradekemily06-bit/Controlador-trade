from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data.feed import MarketDataProvider, MarketDataRequest
from data.models import Candle
from data.timeframes import get_timeframe_interval, normalize_timeframe


class BiQuoteProvider(MarketDataProvider):
    """Read-only BiQuote OHLC provider with safe aggregation of custom intervals.

    Native base intervals are 1m, 5m, 1h and 1d. Other fixed intervals are
    derived only from complete, contiguous base candles aligned to the target
    bucket. No missing or partial candle is estimated.
    """

    BASE_URL = "https://biquote.io/api"
    BASE_INTERVALS = {
        60: "1m",
        300: "5m",
        3600: "1h",
        86400: "1d",
    }
    MAX_SOURCE_BARS = 1000

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout = timeout_seconds

    @staticmethod
    def _bucket_start(timestamp: datetime, target_seconds: int) -> datetime:
        epoch = int(timestamp.timestamp())
        if target_seconds == 604800:
            # Calendar week starts Monday 00:00 UTC, not Unix epoch Thursday.
            monday_offset = 3 * 86400
            bucket_epoch = ((epoch + monday_offset) // target_seconds) * target_seconds - monday_offset
        else:
            bucket_epoch = (epoch // target_seconds) * target_seconds
        return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)

    @classmethod
    def _source_interval(cls, target_seconds: int) -> tuple[int, str]:
        candidates = sorted(cls.BASE_INTERVALS.items(), reverse=True)
        for seconds, label in candidates:
            if target_seconds >= seconds and target_seconds % seconds == 0:
                return seconds, label
        raise ValueError("timeframe cannot be safely derived from available base intervals")

    @staticmethod
    def _aggregate(
        candles: list[Candle], *, source_seconds: int, target_seconds: int
    ) -> list[Candle]:
        if target_seconds == source_seconds:
            return candles
        expected = target_seconds // source_seconds
        groups: dict[datetime, list[Candle]] = {}
        for candle in candles:
            bucket = BiQuoteProvider._bucket_start(candle.timestamp, target_seconds)
            groups.setdefault(bucket, []).append(candle)

        aggregated: list[Candle] = []
        for bucket, group in sorted(groups.items()):
            group.sort(key=lambda candle: candle.timestamp)
            if len(group) != expected:
                continue
            if group[0].timestamp.astimezone(timezone.utc) != bucket:
                continue
            contiguous = all(
                (group[index].timestamp - group[index - 1].timestamp).total_seconds()
                == source_seconds
                for index in range(1, len(group))
            )
            if not contiguous:
                continue
            aggregated.append(
                Candle(
                    timestamp=group[0].timestamp,
                    open=group[0].open,
                    high=max(item.high for item in group),
                    low=min(item.low for item in group),
                    close=group[-1].close,
                    volume=sum(item.volume for item in group),
                )
            )
        return aggregated

    def fetch(self, request: MarketDataRequest) -> list[Candle]:
        timeframe = normalize_timeframe(request.timeframe)
        target_seconds = int(get_timeframe_interval(timeframe).total_seconds())
        source_seconds, source_timeframe = self._source_interval(target_seconds)
        factor = target_seconds // source_seconds
        source_limit = min(request.limit * factor + factor, self.MAX_SOURCE_BARS)
        query = urlencode({"interval": source_timeframe, "limit": source_limit})
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

        candles.sort(key=lambda candle: candle.timestamp)
        candles = self._aggregate(
            candles,
            source_seconds=source_seconds,
            target_seconds=target_seconds,
        )
        return candles[-request.limit:]
