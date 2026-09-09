from datetime import datetime, timezone

import pytest

from core.p122_broker_market_data import (
    BrokerMarketDataBoundary,
    BrokerMarketDataRequest,
)
from data.models import Candle


BASE = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def candle_at(minute: int) -> Candle:
    return Candle(BASE.replace(minute=minute), 100, 101, 99, 100, 10)


class FakeProvider:
    def __init__(self, candles):
        self.candles = candles

    def fetch_market_data(self, request):
        return self.candles


def test_valid_market_data_is_normalized_and_limited():
    provider = FakeProvider([candle_at(0), candle_at(1), candle_at(2)])
    boundary = BrokerMarketDataBoundary(provider, "demo-broker")

    result = boundary.fetch(
        BrokerMarketDataRequest("EURUSD", "1m", 2),
        received_at=BASE,
    )

    assert result.symbol == "EURUSD"
    assert result.timeframe == "1m"
    assert len(result.candles) == 2
    assert result.candles[-1].timestamp == candle_at(2).timestamp
    assert result.source == "demo-broker"
    assert result.received_at == BASE


def test_empty_provider_fails_closed():
    boundary = BrokerMarketDataBoundary(FakeProvider([]), "demo-broker")
    with pytest.raises(ValueError):
        boundary.fetch(BrokerMarketDataRequest("EURUSD", "1m", 2))


def test_none_provider_result_fails_closed():
    boundary = BrokerMarketDataBoundary(FakeProvider(None), "demo-broker")
    with pytest.raises(ValueError):
        boundary.fetch(BrokerMarketDataRequest("EURUSD", "1m", 2))


def test_invalid_request_fails_closed():
    with pytest.raises(ValueError):
        BrokerMarketDataRequest("", "1m", 2)
    with pytest.raises(ValueError):
        BrokerMarketDataRequest("EURUSD", "", 2)
    with pytest.raises(ValueError):
        BrokerMarketDataRequest("EURUSD", "1m", 0)


def test_provider_invalid_sequence_is_rejected():
    invalid = [candle_at(1), candle_at(0)]
    boundary = BrokerMarketDataBoundary(FakeProvider(invalid), "demo-broker")
    with pytest.raises(ValueError):
        boundary.fetch(BrokerMarketDataRequest("EURUSD", "1m", 2))


def test_source_and_provider_are_required():
    with pytest.raises(ValueError):
        BrokerMarketDataBoundary(None, "demo-broker")
    with pytest.raises(ValueError):
        BrokerMarketDataBoundary(FakeProvider([]), " ")
