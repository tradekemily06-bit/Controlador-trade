from datetime import datetime, timedelta, timezone

import pytest

from data.feed import MarketDataFeed, MarketDataRequest
from data.models import Candle


class Provider:
    def __init__(self, candles):
        self.candles = candles

    def fetch(self, request):
        return self.candles


def candles(count=3):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(start + timedelta(minutes=i), 100 + i, 101 + i, 99 + i, 100.5 + i, 10)
        for i in range(count)
    ]


def test_request_validates_inputs():
    assert MarketDataRequest("EURUSD", "1m", 3).limit == 3
    with pytest.raises(ValueError):
        MarketDataRequest("", "1m", 3)
    with pytest.raises(ValueError):
        MarketDataRequest("EURUSD", "1m", 0)


def test_feed_normalizes_valid_provider_data_and_applies_limit():
    result = MarketDataFeed(Provider(candles(5)), source="paper").fetch(
        MarketDataRequest("EURUSD", "1m", 3),
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(result.candles) == 3
    assert result.candles[0].close == 102.5
    assert result.source == "paper"


def test_feed_rejects_empty_provider_response():
    with pytest.raises(ValueError, match="no candles"):
        MarketDataFeed(Provider([])).fetch(MarketDataRequest("EURUSD", "1m", 1))


def test_feed_rejects_invalid_sequence():
    data = candles(2)
    data[1] = Candle(data[1].timestamp, 1, 0, 2, 1, 1)
    with pytest.raises(ValueError):
        MarketDataFeed(Provider(data)).fetch(MarketDataRequest("EURUSD", "1m", 2))


def test_feed_rejects_non_chronological_data():
    data = candles(3)
    data[1], data[2] = data[2], data[1]
    with pytest.raises(ValueError):
        MarketDataFeed(Provider(data)).fetch(MarketDataRequest("EURUSD", "1m", 3))


def test_feed_rejects_duplicate_timestamps():
    data = candles(3)
    data[2] = Candle(data[1].timestamp, 102, 103, 101, 102.5, 10)
    with pytest.raises(ValueError, match="invalid candle sequence"):
        MarketDataFeed(Provider(data)).fetch(MarketDataRequest("EURUSD", "1m", 3))


def test_feed_validates_before_applying_limit():
    data = candles(3)
    data[-1] = Candle(data[-1].timestamp, 1, 0, 2, 1, 1)
    with pytest.raises(ValueError, match="invalid candle sequence"):
        MarketDataFeed(Provider(data)).fetch(MarketDataRequest("EURUSD", "1m", 2))
