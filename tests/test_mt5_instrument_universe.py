from __future__ import annotations

from types import SimpleNamespace

from execution.mt5_instrument_universe import (
    discover_mt5_instruments,
    eligible_mt5_instruments,
)


class FakeMT5:
    SYMBOL_TRADE_MODE_DISABLED = 0
    SYMBOL_TRADE_MODE_CLOSEONLY = 3

    def __init__(self) -> None:
        self._info = {
            "SOLUSD": SimpleNamespace(name="SOLUSD", visible=True, trade_mode=1),
            "LTCUSD": SimpleNamespace(name="LTCUSD", visible=True, trade_mode=1),
            "EURUSD": SimpleNamespace(name="EURUSD", visible=True, trade_mode=1),
            "CLOSED": SimpleNamespace(name="CLOSED", visible=True, trade_mode=1),
            "DISABLED": SimpleNamespace(name="DISABLED", visible=True, trade_mode=0),
        }

    def symbols_get(self):
        return tuple(self._info.values())

    def symbol_info(self, symbol):
        return self._info[symbol]

    def symbol_info_tick(self, symbol):
        if symbol == "CLOSED":
            return SimpleNamespace(bid=0, ask=0, last=0)
        return SimpleNamespace(bid=100, ask=101, last=100.5)

    def symbol_info_session_trade(self, symbol, day, index):
        if index > 0:
            return None
        if symbol == "CLOSED":
            return SimpleNamespace(**{"from": 0, "to": 60})
        return SimpleNamespace(**{"from": 0, "to": 86399})


def test_discovers_multiple_assets_and_marks_crypto_weekend_capable() -> None:
    statuses = discover_mt5_instruments(
        FakeMT5(),
        now=__import__("datetime").datetime(2026, 9, 12, 12, 0),
    )

    by_symbol = {item.symbol: item for item in statuses}
    assert by_symbol["SOLUSD"].asset_class == "crypto"
    assert by_symbol["LTCUSD"].weekend_capable is True
    assert by_symbol["EURUSD"].asset_class == "other"
    assert by_symbol["CLOSED"].state == "CLOSED"
    assert by_symbol["DISABLED"].state == "DISABLED"


def test_eligible_instruments_exclude_closed_and_disabled() -> None:
    statuses = discover_mt5_instruments(FakeMT5())
    eligible = {item.symbol for item in eligible_mt5_instruments(statuses)}

    assert {"SOLUSD", "LTCUSD", "EURUSD"}.issubset(eligible)
    assert "CLOSED" not in eligible
    assert "DISABLED" not in eligible
