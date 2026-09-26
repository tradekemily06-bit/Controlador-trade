from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.p122_broker_market_data import BrokerMarketDataRequest
from data.feed import MarketDataRequest
from integration.mt5_runtime_feed import ICMarketsMT5DemoRuntimeProvider


@dataclass
class _Account:
    trade_mode: int


class _MT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TIMEFRAME_M5 = 5

    def __init__(self):
        self.shutdown_called = False

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def account_info(self):
        return _Account(self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, enabled):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return [
            {
                "time": 1_700_000_000,
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.05,
                "tick_volume": 100,
                "real_volume": 100,
            }
        ]


def test_mt5_runtime_provider_uses_demo_adapter():
    mt5 = _MT5()
    provider = ICMarketsMT5DemoRuntimeProvider(mt5_module=mt5)

    candles = provider.fetch(MarketDataRequest("EURUSD", "5m", 10))

    assert len(candles) == 1
    assert candles[0].close == 1.05
    assert mt5.shutdown_called is True


def test_mt5_runtime_provider_rejects_invalid_request():
    provider = ICMarketsMT5DemoRuntimeProvider(mt5_module=_MT5())

    with pytest.raises(TypeError, match="MarketDataRequest"):
        provider.fetch(BrokerMarketDataRequest("EURUSD", "5m", 10))
