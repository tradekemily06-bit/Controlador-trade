from __future__ import annotations

from dataclasses import dataclass

from integration.ecosystem_service import EcosystemService


@dataclass
class _Account:
    trade_mode: int


class _MT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TIMEFRAME_M5 = 5

    def initialize(self):
        return True

    def shutdown(self):
        return None

    def account_info(self):
        return _Account(self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, enabled):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return [{
            "time": 1_700_000_000,
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.05,
            "tick_volume": 100,
            "real_volume": 100,
        }]


def test_service_reads_mt5_demo_completed_candles():
    result = EcosystemService().mt5_market_data(
        symbol="EURUSD",
        timeframe="5m",
        limit=10,
        mt5_module=_MT5(),
    )

    assert result["source"] == "IC Markets MT5 DEMO"
    assert result["execution_allowed"] is False
    assert len(result["candles"]) == 1
    assert result["candles"][0]["close"] == 1.05
