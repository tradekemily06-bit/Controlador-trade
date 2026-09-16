from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 1
    TRADE_ACTION_DEAL = 10
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.sent = 0
        self.selected = []

    def initialize(self):
        return True

    def shutdown(self):
        return None

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, enabled):
        self.selected.append((symbol, enabled))
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=100.0, bid=99.9)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0)

    def order_send(self, payload):
        self.sent += 1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=12345, deal=54321)

    def last_error(self):
        return (0, "ok")


def _request(symbol="EURUSD"):
    return ExecutionRequest(
        symbol, Signal.COMPRA, 0.01, 60, ExecutionMode.DEMO, request_id="demo-identity",
    )


def test_configured_symbol_cannot_override_request_symbol():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol="XAUUSD"), mt5_module=mt5)
    result = adapter.execute(_request("EURUSD"))
    assert result.accepted is False
    assert mt5.sent == 0
    assert mt5.selected == []


def test_matching_configured_symbol_is_preserved_through_order_payload():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol="EURUSD"), mt5_module=mt5)
    result = adapter.execute(_request("EURUSD"))
    assert result.accepted is True
    assert result.external_id == "12345"
    assert mt5.sent == 1
    assert mt5.selected == [("EURUSD", True)]


def test_adapter_rejects_real_even_with_valid_market_identity():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol="EURUSD"), mt5_module=mt5)
    request = ExecutionRequest("EURUSD", Signal.COMPRA, 0.01, 60, ExecutionMode.REAL, request_id="real-block")
    result = adapter.execute(request)
    assert result.accepted is False
    assert mt5.sent == 0
