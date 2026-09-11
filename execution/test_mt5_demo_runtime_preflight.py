from __future__ import annotations

from types import SimpleNamespace

from execution.mt5_demo_runtime_preflight import run_preflight


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2

    def __init__(self, *, demo: bool = True, symbol_ok: bool = True, tick_ok: bool = True) -> None:
        self.demo = demo
        self.symbol_ok = symbol_ok
        self.tick_ok = tick_ok
        self.shutdown_called = False

    def initialize(self) -> bool:
        return True

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 0)

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return self.symbol_ok

    def symbol_info(self, symbol: str):
        if not self.tick_ok:
            return None
        return SimpleNamespace(volume_min=0.01, volume_step=0.01)

    def symbol_info_tick(self, symbol: str):
        if not self.tick_ok:
            return None
        return SimpleNamespace(bid=1.16065, ask=1.16066)

    def shutdown(self) -> None:
        self.shutdown_called = True

    def last_error(self):
        return (-1, "fake error")


def test_preflight_accepts_demo_symbol_quote_and_volume_limits() -> None:
    mt5 = FakeMT5()
    result = run_preflight(mt5)
    assert result.available is True
    assert result.demo is True
    assert result.symbol == "EURUSD"
    assert result.bid == 1.16065
    assert result.ask == 1.16066
    assert result.volume_min == 0.01
    assert result.volume_step == 0.01
    assert mt5.shutdown_called is True


def test_preflight_rejects_non_demo_account() -> None:
    result = run_preflight(FakeMT5(demo=False))
    assert result.available is False
    assert result.demo is False
    assert "DEMO" in result.message


def test_preflight_rejects_unavailable_symbol() -> None:
    result = run_preflight(FakeMT5(symbol_ok=False))
    assert result.available is False
    assert result.demo is True
    assert "símbolo não disponível" in result.message


def test_preflight_rejects_missing_quote_or_metadata() -> None:
    result = run_preflight(FakeMT5(tick_ok=False))
    assert result.available is False
    assert result.demo is True
    assert "cotação/metadados indisponíveis" in result.message
