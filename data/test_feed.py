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


def test_feed_overlays_same_timestamp_live_closed_candle():
    history = candles(3)
    live = Candle(history[-1].timestamp, 102, 104, 101, 103.5, 25)
    result = MarketDataFeed(Provider(history), source="stream").fetch(
        MarketDataRequest("EURUSD", "1m", 3), live_candle=live
    )
    assert result.candles[-1].close == 103.5
    assert result.candles[-1].volume == 25


def test_feed_appends_only_contiguous_live_candle():
    history = candles(3)
    live = Candle(history[-1].timestamp + timedelta(minutes=1), 103, 105, 102, 104.5, 30)
    result = MarketDataFeed(Provider(history), source="stream").fetch(
        MarketDataRequest("EURUSD", "1m", 4), live_candle=live
    )
    assert len(result.candles) == 4
    assert result.candles[-1] == live


def test_feed_rejects_live_candle_with_history_gap():
    history = candles(3)
    live = Candle(history[-1].timestamp + timedelta(minutes=2), 103, 105, 102, 104.5, 30)
    with pytest.raises(ValueError, match="not contiguous"):
        MarketDataFeed(Provider(history), source="stream").fetch(
            MarketDataRequest("EURUSD", "1m", 4), live_candle=live
        )


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
    with pytest.raises(ValueError, match="Dados de candle inválidos"):
        MarketDataFeed(Provider(data)).fetch(MarketDataRequest("EURUSD", "1m", 2))
