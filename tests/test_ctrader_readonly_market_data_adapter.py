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
        return {
            "symbol_id": 44,
            "digits": 5,
            "schedule_time_zone": "Europe/London",
            "schedule": ({"start_second": 3600, "end_second": 604800},),
            "holidays": (),
            "calendar_metadata_status": "AVAILABLE",
        }

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

    def update_access_token(self, access_token):
        self.calls.append(("update_access_token", access_token))

    def disconnect(self):
        self.connected = False


def test_ctrader_exposes_broker_schedule_metadata_without_enabling_d1_w1():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    calendar = adapter.get_symbol_session_calendar_metadata("EURUSD")

    assert calendar["provider_id"] == "ctrader_open_api"
    assert calendar["account_id"] == 123
    assert calendar["schedule_time_zone"] == "Europe/London"
    assert calendar["schedule"] == ({"start_second": 3600, "end_second": 604800},)
    assert calendar["holidays"] == ()
    assert calendar["status"] == "METADATA_AVAILABLE_NOT_CALENDAR_VALIDATED"
    # Schedule metadata is not proof of how this broker aggregates D1/W1 bars.
    assert not callable(getattr(adapter, "expected_last_closed_candle", None))


@pytest.mark.parametrize(
    "metadata",
    [
        {"schedule_time_zone": None, "schedule": ({"start_second": 0, "end_second": 604800},), "holidays": (), "calendar_metadata_status": "AVAILABLE"},
        {"schedule_time_zone": "Europe/London", "schedule": ({"start_second": 604800, "end_second": 604800},), "holidays": (), "calendar_metadata_status": "AVAILABLE"},
        {"schedule_time_zone": "Europe/London", "schedule": (), "holidays": (), "calendar_metadata_status": "AVAILABLE"},
    ],
)
def test_ctrader_incomplete_or_invalid_schedule_metadata_is_not_exposed(metadata):
    transport = FakeTransport()
    transport.resolve_symbol = lambda account_id, symbol: {
        "symbol_id": 44, "digits": 5, **metadata
    }
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    assert adapter.get_symbol_session_calendar_metadata("EURUSD") is None


@pytest.mark.parametrize(
    "holiday",
    [
        {"name": "Holiday", "holiday_date": 20000, "is_recurring": False, "schedule_time_zone": ""},
        {"name": "Holiday", "holiday_date": True, "is_recurring": False, "schedule_time_zone": "UTC"},
        {"name": "Holiday", "holiday_date": 20000, "is_recurring": "false", "schedule_time_zone": "UTC"},
        {"name": "Holiday", "holiday_date": 20000, "is_recurring": False, "schedule_time_zone": "Not/A_Real_Zone"},
        {"name": "Holiday", "holiday_date": 20000, "is_recurring": False, "schedule_time_zone": "UTC", "start_second": 90000},
        {"name": "Holiday", "holiday_date": 20000, "is_recurring": False, "schedule_time_zone": "UTC", "start_second": 500, "end_second": 400},
    ],
)
def test_ctrader_invalid_holiday_metadata_is_not_exposed(holiday):
    transport = FakeTransport()
    transport.resolve_symbol = lambda account_id, symbol: {
        "symbol_id": 44,
        "digits": 5,
        "schedule_time_zone": "Europe/London",
        "schedule": ({"start_second": 3600, "end_second": 604800},),
        "holidays": (holiday,),
        "calendar_metadata_status": "AVAILABLE",
    }
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    assert adapter.get_symbol_session_calendar_metadata("EURUSD") is None


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


def test_ctrader_adapter_reconnect_requires_demo_confirmation():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    adapter._connected = False
    adapter._authenticated = False
    transport.reconnect = lambda: {"account_id": 123, "is_live": False}

    result = adapter.reconnect()
    assert result["account_mode"] == "DEMO"
    assert adapter.status()["connected"] is True
    assert adapter.status()["execution_authorized"] is False


def test_ctrader_adapter_failed_reconnect_does_not_report_demo_connected():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    adapter._connected = False
    transport.reconnect = lambda: (_ for _ in ()).throw(OSError("offline"))

    with pytest.raises(OSError, match="offline"):
        adapter.reconnect()
    assert adapter.status()["connected"] is False
    assert adapter.status()["account_mode"] is None


def test_ctrader_adapter_refreshes_tenant_vault_token_before_reconnect():
    transport = FakeTransport()
    resolved = []
    adapter = CTraderReadOnlyMarketDataAdapter(
        transport,
        account_id=123,
        access_token_resolver=lambda: resolved.append("vault-token-rotated") or "vault-token-rotated",
    )
    adapter.connect()
    adapter.handshake()
    adapter._connected = False
    adapter._authenticated = False
    transport.reconnect = lambda: {"account_id": 123, "is_live": False}

    result = adapter.reconnect()

    assert resolved == ["vault-token-rotated"]
    assert ("update_access_token", "vault-token-rotated") in transport.calls
    assert result["account_mode"] == "DEMO"
    assert adapter.status()["connected"] is True


def test_ctrader_adapter_fails_closed_when_refreshed_token_unavailable():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(
        transport, account_id=123, access_token_resolver=lambda: None,
    )
    adapter.connect()
    adapter.handshake()
    adapter._connected = False
    adapter._authenticated = False
    transport.reconnect = lambda: {"account_id": 123, "is_live": False}

    with pytest.raises(PermissionError, match="token OAuth cTrader renovado indisponível"):
        adapter.reconnect()
    assert adapter.status()["connected"] is False


@pytest.mark.parametrize("bad_field", [True, "110000", 10 ** 1000])
def test_ctrader_rejects_non_integer_trendbar_price_fields(bad_field):
    transport = FakeTransport()
    transport.get_trendbars = lambda *args: [{
        "low": bad_field,
        "deltaOpen": 1000,
        "deltaHigh": 3000,
        "deltaClose": 2000,
        "utcTimestampInMinutes": 30000000,
        "volume": 125,
    }]
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    with pytest.raises(ValueError, match="trendbar"):
        adapter.fetch(MarketDataRequest("EURUSD", "5m", 20))


@pytest.mark.parametrize("bad_volume", [True, "125", float("nan"), float("inf"), 10 ** 1000])
def test_ctrader_rejects_non_finite_or_non_numeric_volume(bad_volume):
    transport = FakeTransport()
    transport.get_trendbars = lambda *args: [{
        "low": 110000,
        "deltaOpen": 1000,
        "deltaHigh": 3000,
        "deltaClose": 2000,
        "utcTimestampInMinutes": 30000000,
        "volume": bad_volume,
    }]
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    with pytest.raises(ValueError, match="trendbar"):
        adapter.fetch(MarketDataRequest("EURUSD", "5m", 20))


def test_ctrader_drops_boolean_or_non_finite_live_quote_values():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []
    adapter.subscribe_live_quotes("EURUSD", received.append)

    transport.spot_callback({"symbol_id": 44, "bid": True, "ask": 110145, "timestamp": 1800000000})
    transport.spot_callback({"symbol_id": 44, "bid": 110123, "ask": None, "timestamp": float("nan")})

    assert received == []


@pytest.mark.parametrize("quote", [
    {"bid": 0, "ask": 110145},
    {"bid": -1, "ask": 110145},
    {"bid": 110123, "ask": 0},
    {"bid": 110123, "ask": -1},
])
def test_ctrader_drops_non_positive_live_quotes(quote):
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []
    adapter.subscribe_live_quotes("EURUSD", received.append)

    transport.spot_callback({"symbol_id": 44, **quote, "timestamp": 1800000000})

    assert received == []


def test_ctrader_drops_crossed_live_bid_ask_quote():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()
    received = []
    adapter.subscribe_live_quotes("EURUSD", received.append)

    transport.spot_callback({
        "symbol_id": 44, "bid": 110200, "ask": 110100,
        "timestamp": 1800000000,
    })

    assert received == []


@pytest.mark.parametrize("returned_id", [True, "123", 123.0, None])
def test_ctrader_handshake_rejects_coerced_account_identity(returned_id):
    transport = FakeTransport()
    transport.account_details = lambda account_id: {
        "account_id": returned_id,
        "is_live": False,
    }
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()

    with pytest.raises(PermissionError, match="identificador de conta inválido"):
        adapter.handshake()

    assert adapter.status()["connected"] is False

@pytest.mark.parametrize("timeframe", ["1m", "M1", "5m", "M5", "1h", "H1", "1d", "D1"])
def test_ctrader_declares_supported_timeframes(timeframe):
    assert CTraderReadOnlyMarketDataAdapter.supports_timeframe(timeframe) is True


@pytest.mark.parametrize("timeframe", ["2m", "M2", "7m", "unknown"])
def test_ctrader_does_not_declare_unsupported_timeframes(timeframe):
    assert CTraderReadOnlyMarketDataAdapter.supports_timeframe(timeframe) is False



def test_ctrader_adapter_normalizes_platform_timeframe_aliases_at_every_boundary():
    transport = FakeTransport()
    adapter = CTraderReadOnlyMarketDataAdapter(transport, account_id=123)
    adapter.connect()
    adapter.handshake()

    adapter.fetch(MarketDataRequest("EURUSD", "M1", 10))
    assert transport.calls[-1] == ("bars", 123, 44, "M1", 10)

    received = []
    adapter.subscribe_live_candles("EURUSD", "M5", received.append)
    assert ("subscribe_live_trendbars", 123, 44, "M5") in transport.calls
    adapter.unsubscribe_live_candles("EURUSD", "M5")
    assert transport.calls[-1] == ("unsubscribe_live_trendbars", 123, 44, "M5")
