from types import SimpleNamespace

from execution.mt5_instrument_universe import discover_mt5_instruments


class FakeMT5:
    SYMBOL_TRADE_MODE_DISABLED = 0
    SYMBOL_TRADE_MODE_CLOSEONLY = 1
    SYMBOL_CALC_MODE_FOREX = 10
    SYMBOL_CALC_MODE_FUTURES = 11
    SYMBOL_CALC_MODE_CFDINDEX = 12
    SYMBOL_CALC_MODE_EXCH_STOCKS = 13
    SYMBOL_CALC_MODE_CFD_BONDS = 14

    def __init__(self, *, weekend=False):
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.weekend = weekend
        self.items = [
            SimpleNamespace(name="EURUSD"),
            SimpleNamespace(name="XAUUSD"),
            SimpleNamespace(name="US500"),
            SimpleNamespace(name="AAPL"),
            SimpleNamespace(name="BTCUSD"),
            SimpleNamespace(name="UNKNOWN1"),
        ]
        self.info = {
            "EURUSD": SimpleNamespace(path="Forex\\Majors", description="Euro vs US Dollar", trade_mode=2, trade_calc_mode=10, visible=True),
            "XAUUSD": SimpleNamespace(path="Commodities\\Metals", description="Gold", trade_mode=2, trade_calc_mode=99, visible=True),
            "US500": SimpleNamespace(path="Indices", description="US 500", trade_mode=2, trade_calc_mode=12, visible=True),
            "AAPL": SimpleNamespace(path="Stocks", description="Apple", trade_mode=2, trade_calc_mode=13, visible=True),
            "BTCUSD": SimpleNamespace(path="Crypto", description="Bitcoin", trade_mode=2, trade_calc_mode=99, visible=True),
            "UNKNOWN1": SimpleNamespace(path="", description="", trade_mode=2, trade_calc_mode=99, visible=True),
        }

    def initialize(self):
        self.initialize_calls += 1
        return True

    def shutdown(self):
        self.shutdown_calls += 1

    def symbols_get(self):
        return self.items

    def symbol_info(self, symbol):
        return self.info[symbol]

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.0, ask=1.1, last=1.05)

    def symbol_info_session_trade(self, symbol, day, index):
        if index > 0:
            return None
        if day in (0, 6) and not self.weekend:
            return None
        return SimpleNamespace(**{"from": 0, "to": 86399})


def test_discovers_major_asset_classes_and_unknown_without_static_whitelist():
    statuses = discover_mt5_instruments(FakeMT5(), include_invisible=True)
    classes = {item.symbol: item.asset_class for item in statuses}

    assert classes["EURUSD"] == "forex"
    assert classes["XAUUSD"] == "commodity"
    assert classes["US500"] == "index"
    assert classes["AAPL"] == "stock"
    assert classes["BTCUSD"] == "crypto"
    assert classes["UNKNOWN1"] == "other"
    assert len(statuses) == 6


def test_weekend_capability_comes_from_broker_session_when_available():
    weekday = discover_mt5_instruments(FakeMT5(weekend=False), include_invisible=True)
    weekend = discover_mt5_instruments(FakeMT5(weekend=True), include_invisible=True)

    weekday_by_symbol = {item.symbol: item.weekend_capable for item in weekday}
    weekend_by_symbol = {item.symbol: item.weekend_capable for item in weekend}

    assert weekday_by_symbol["EURUSD"] is False
    assert weekend_by_symbol["EURUSD"] is True
    assert weekend_by_symbol["BTCUSD"] is True
