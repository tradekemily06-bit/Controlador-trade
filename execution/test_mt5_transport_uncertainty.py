from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    ORDER_TYPE_BUY = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, result_none=False):
        self.result_none = result_none

    def initialize(self):
        return True

    def shutdown(self):
        pass

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=100.0, bid=99.0)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0)

    def order_send(self, payload):
        if self.result_none:
            return None
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=123, deal=456)

    def last_error(self):
        return (1, "transport uncertainty")


def request():
    return ExecutionRequest(
        "EURUSD", Signal.COMPRA, 0.01, 60, ExecutionMode.DEMO, request_id="uncertain-1"
    )


def test_part6_mt5_missing_send_result_is_uncertain_not_rejected():
    result = ICMarketsMT5DemoAdapter(mt5_module=FakeMT5(result_none=True)).execute(request())
    assert result.accepted is False
    assert result.uncertain is True
