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


def test_missing_broker_session_metadata_does_not_claim_crypto_is_weekend_capable():
    mt5 = FakeMT5(weekend=False)
    mt5.symbol_info_session_trade = None

    statuses = discover_mt5_instruments(mt5, include_invisible=True)
    by_symbol = {item.symbol: item for item in statuses}

    assert by_symbol["BTCUSD"].asset_class == "crypto"
    assert by_symbol["BTCUSD"].weekend_capable is False


def test_instrument_catalog_exposes_broker_currency_and_contract_metadata():
    mt5 = FakeMT5()
    mt5.info["EURUSD"].currency_base = "EUR"
    mt5.info["EURUSD"].currency_profit = "USD"
    mt5.info["EURUSD"].currency_margin = "USD"
    mt5.info["EURUSD"].trade_contract_size = 100000.0
    mt5.info["EURUSD"].digits = 5
    mt5.info["EURUSD"].point = 0.00001
    mt5.info["EURUSD"].trade_tick_size = 0.00001
    mt5.info["EURUSD"].trade_tick_value = 1.0

    statuses = discover_mt5_instruments(mt5, include_invisible=True)
    eurusd = next(item for item in statuses if item.symbol == "EURUSD")

    assert eurusd.currency_base == "EUR"
    assert eurusd.currency_profit == "USD"
    assert eurusd.currency_margin == "USD"
    assert eurusd.contract_size == 100000.0
    assert eurusd.digits == 5
    assert eurusd.point == 0.00001
    assert eurusd.trade_tick_size == 0.00001
    assert eurusd.trade_tick_value == 1.0


def test_invalid_broker_currency_and_numeric_metadata_are_omitted():
    mt5 = FakeMT5()
    mt5.info["EURUSD"].currency_base = "EU1"
    mt5.info["EURUSD"].currency_profit = "USDD"
    mt5.info["EURUSD"].trade_contract_size = float("nan")
    mt5.info["EURUSD"].digits = True

    statuses = discover_mt5_instruments(mt5, include_invisible=True)
    eurusd = next(item for item in statuses if item.symbol == "EURUSD")

    assert eurusd.currency_base is None
    assert eurusd.currency_profit is None
    assert eurusd.contract_size is None
    assert eurusd.digits is None
