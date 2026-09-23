from __future__ import annotations

from types import SimpleNamespace

from core.models import Signal
from execution.mt5_real_adapter import MT5RealAdapter, MT5RealConfig
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self) -> None:
        self.initialized = False
        self.shutdowns = 0
        self.sent = 0

    def initialize(self):
        self.initialized = True
        return True

    def shutdown(self):
        self.shutdowns += 1

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_REAL, server="Broker-Real")

    def symbol_select(self, symbol, enabled):
        return enabled

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=100.0, bid=99.9)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0)

    def order_send(self, payload):
        self.sent += 1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=987654)

    def last_error(self):
        return (0, "ok")


def request(mode=ExecutionMode.REAL):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=mode,
    )


def test_real_adapter_accepts_only_real_accounts():
    mt5 = FakeMT5()
    adapter = MT5RealAdapter(MT5RealConfig(expected_server="Broker-Real"), mt5)
    assert adapter.is_available() is True

    result = adapter.execute(request())
    assert result.accepted is True
    assert result.external_id == "987654"
    assert mt5.sent == 1
    assert mt5.shutdowns == 0
    adapter.disconnect()
    assert mt5.shutdowns == 1


def test_real_adapter_rejects_demo_requests_without_sending():
    mt5 = FakeMT5()
    adapter = MT5RealAdapter(mt5_module=mt5)

    result = adapter.execute(request(ExecutionMode.DEMO))

    assert result.accepted is False
    assert mt5.sent == 0


def test_real_adapter_blocks_server_mismatch():
    mt5 = FakeMT5()
    adapter = MT5RealAdapter(MT5RealConfig(expected_server="Other-Broker"), mt5)

    assert adapter.is_available() is False
    result = adapter.execute(request())
    assert result.accepted is False
    assert mt5.sent == 0
