from datetime import datetime, timezone

import pytest

from data.feed import MarketDataRequest
from integration.ctrader_readonly_market_data_adapter import CTraderReadOnlyMarketDataAdapter


class FakeTransport:
    def __init__(self, *, is_live=False):
        self.is_live = is_live
        self.calls = []
        self.connected = False

    def connect(self):
        self.connected = True

    def application_auth(self):
        self.calls.append("app_auth")

    def account_details(self, account_id):
        return {"account_id": account_id, "is_live": self.is_live}

    def account_auth(self, account_id):
        self.calls.append(("account_auth", account_id))

    def resolve_symbol(self, account_id, symbol):
        self.calls.append(("resolve", account_id, symbol))
        return {"symbol_id": 44, "digits": 5}

    def get_trendbars(self, account_id, symbol_id, period, count):
        self.calls.append(("bars", account_id, symbol_id, period, count))
        return [{
            "low": 110000,
            "deltaOpen": 1000,
            "deltaHigh": 3000,
            "deltaClose": 2000,
            "utcTimestampInMinutes": 30000000,
            "volume": 125,
        }]

    def subscribe_spots(self, account_id, symbol_id, callback):
        self.calls.append(("subscribe_spots", account_id, symbol_id))
        self.spot_callback = callback

    def unsubscribe_spots(self, account_id, symbol_id):
        self.calls.append(("unsubscribe_spots", account_id, symbol_id))

    def subscribe_live_trendbars(self, account_id, symbol_id, period, callback):
        self.calls.append(("subscribe_live_trendbars", account_id, symbol_id, period))
        self.trendbar_callback = callback

    def unsubscribe_live_trendbars(self, account_id, symbol_id, period):
        self.calls.append(("unsubscribe_live_trendbars", account_id, symbol_id, period))

    def status(self):
        return {"connected": True, "last_seen": datetime.now(timezone.utc).isoformat()}

    def disconnect(self):
        self.connected = False


def test_ctrader_adapter_verifies_demo_and_normalizes_trendbars():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    handshake = adapter.handshake()

    candles = adapter.fetch(MarketDataRequest("EURUSD", "5m", 20))

    assert handshake["provider_id"] == "ctrader_open_api"
    assert handshake["verified"] is True
    assert candles[0].low == 1.1
    assert candles[0].open == 1.11
    assert candles[0].high == 1.13
    assert candles[0].close == 1.12
    assert candles[0].volume == 125
    assert transport.calls[-1] == ("bars", 123, 44, "M5", 20)
    assert adapter.status()["account_mode"] == "DEMO"
    assert adapter.status()["execution_authorized"] is False


def test_ctrader_adapter_rejects_live_account_and_non_supported_timeframe():
    live = CTraderReadOnlyMarketDataAdapter(FakeTransport(is_live=True), account_id=123)
    live.connect()
    with pytest.raises(PermissionError, match="somente conta cTrader DEMO"):
        live.handshake()

    demo = CTraderReadOnlyMarketDataAdapter(FakeTransport(), account_id=123)
    demo.connect()
    demo.handshake()
    with pytest.raises(ValueError, match="timeframe"):
        demo.fetch(MarketDataRequest("EURUSD", "2m", 10))


def test_ctrader_adapter_requires_handshake_before_market_data():
    adapter = CTraderReadOnlyMarketDataAdapter(FakeTransport(), account_id=123)
    with pytest.raises(RuntimeError, match="handshake"):
        adapter.fetch(MarketDataRequest("EURUSD", "1m", 10))



def test_ctrader_adapter_streams_normalized_live_quotes_and_unsubscribes():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []

    adapter.subscribe_live_quotes("EURUSD", received.append)
    transport.spot_callback({
        "symbol_id": 44,
        "bid": 110123,
        "ask": 110145,
        "timestamp": 1_800_000_000_000,
    })

    assert received[0]["provider_id"] == "ctrader_open_api"
    assert received[0]["account_id"] == 123
    assert received[0]["symbol"] == "EURUSD"
    assert received[0]["bid"] == 1.10123
    assert received[0]["ask"] == 1.10145
    assert received[0]["timestamp"].startswith("2027-")
    assert received[0]["read_only"] is True
    assert received[0]["execution_authorized"] is False

    adapter.unsubscribe_live_quotes("EURUSD")
    assert transport.calls[-1] == ("unsubscribe_spots", 123, 44)


def test_ctrader_adapter_ignores_malformed_live_quote_without_crashing():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []
    adapter.subscribe_live_quotes("EURUSD", received.append)
    transport.spot_callback({"symbol_id": 44, "bid": "invalid", "ask": None})
    assert received == []



def test_ctrader_adapter_streams_only_normalized_closed_trendbars():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    handshake = adapter.handshake()
    received = []

    adapter.subscribe_live_candles("EURUSD", "5m", received.append)
    assert ("subscribe_live_trendbars", 123, 44, "M5") in transport.calls
    transport.trendbar_callback({
        "symbol_id": 44,
        "period": "M5",
        "trendbar": {
            "low": 110000,
            "deltaOpen": 1000,
            "deltaHigh": 3000,
            "deltaClose": 2000,
            "utcTimestampInMinutes": 30000000,
            "volume": 125,
        },
    })

    assert "candles:stream" in handshake["capabilities"]
    assert len(received) == 1
    event = received[0]
    assert event["closed"] is True
    assert event["execution_authorized"] is False
    assert event["candle"].low == 1.1
    assert event["candle"].open == 1.11
    assert event["candle"].high == 1.13
    assert event["candle"].close == 1.12

    adapter.unsubscribe_live_candles("EURUSD", "5m")
    assert transport.calls[-1] == ("unsubscribe_live_trendbars", 123, 44, "M5")


def test_ctrader_adapter_drops_invalid_live_trendbar():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []
    adapter.subscribe_live_candles("EURUSD", "1m", received.append)
    transport.trendbar_callback({
        "symbol_id": 44,
        "period": "M1",
        "trendbar": {"low": "bad"},
    })
    assert received == []
