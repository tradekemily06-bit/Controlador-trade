from types import SimpleNamespace

import pytest

from core.p122_broker_market_data import BrokerMarketDataRequest
from execution.icmarkets_mt5_market_data import (
    ICMarketsMT5DemoMarketDataAdapter,
    MT5MarketDataError,
)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TIMEFRAME_M5 = 5

    def __init__(self, *, demo=True, rates=None):
        self.demo = demo
        self.rates = rates or []
        self.initialized = False
        self.shutdown_called = False
        self.selected = []

    def initialize(self):
        self.initialized = True
        return True

    def shutdown(self):
        self.shutdown_called = True

    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 1
        )

    def symbol_select(self, symbol, enable):
        self.selected.append((symbol, enable))
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        assert timeframe == self.TIMEFRAME_M5
        assert start_pos == 1
        assert count == 2
        return self.rates[:count]

    def last_error(self):
        return (0, "ok")


@pytest.fixture
def rates():
    return [
        {
            "time": 1720000000,
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "tick_volume": 12,
            "real_volume": 10,
        },
        {
            "time": 1720000300,
            "open": 103.0,
            "high": 106.0,
            "low": 102.0,
            "close": 104.0,
            "tick_volume": 15,
            "real_volume": 13,
        },
    ]


def test_fetch_returns_normalized_completed_candles(rates):
    mt5 = FakeMT5(rates=rates)
    adapter = ICMarketsMT5DemoMarketDataAdapter(mt5)

    candles = adapter.fetch_market_data(
        BrokerMarketDataRequest(symbol="BTCUSD", timeframe="5m", limit=2)
    )

    assert len(candles) == 2
    assert candles[0].open == 100.0
    assert candles[0].close == 103.0
    assert candles[0].volume == 12.0
    assert candles[0].timestamp.tzinfo is not None
    assert mt5.shutdown_called is True
    assert mt5.selected == [("BTCUSD", True)]


def test_real_account_is_blocked_for_market_data(rates):
    mt5 = FakeMT5(demo=False, rates=rates)
    adapter = ICMarketsMT5DemoMarketDataAdapter(mt5)

    with pytest.raises(MT5MarketDataError, match="DEMO"):
        adapter.fetch_market_data(
            BrokerMarketDataRequest(symbol="BTCUSD", timeframe="5m", limit=2)
        )

    assert mt5.shutdown_called is True


def test_unsupported_timeframe_is_rejected():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoMarketDataAdapter(mt5)

    with pytest.raises(ValueError, match="timeframe não suportado"):
        adapter.fetch_market_data(
            BrokerMarketDataRequest(symbol="BTCUSD", timeframe="2m", limit=2)
        )


def test_invalid_request_type_is_rejected():
    adapter = ICMarketsMT5DemoMarketDataAdapter(FakeMT5())

    with pytest.raises(TypeError, match="BrokerMarketDataRequest"):
        adapter.fetch_market_data("BTCUSD")
