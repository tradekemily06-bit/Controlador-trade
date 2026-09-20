from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_TIMEOUT = 10012
    TRADE_RETCODE_ORDER_CHANGED = 10023
    TRADE_RETCODE_LOCKED = 10028

    def __init__(self, retcode=None, result_none=False):
        self.retcode = retcode
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
        return SimpleNamespace(
            retcode=self.retcode,
            order=123,
            deal=456,
        )

    def last_error(self):
        return (1, "transport uncertainty")


def request():
    return ExecutionRequest(
        "EURUSD", Signal.COMPRA, 0.01, 60, ExecutionMode.DEMO, request_id="uncertain-1"
    )


def test_part4_mt5_missing_send_result_is_ambiguous_not_rejected():
    result = ICMarketsMT5DemoAdapter(
        mt5_module=FakeMT5(retcode=FakeMT5.TRADE_RETCODE_DONE, result_none=True)
    ).execute(request())
    assert result.accepted is False
    assert result.ambiguous is True


def test_part4_mt5_nonterminal_trade_codes_are_ambiguous():
    for code in (
        FakeMT5.TRADE_RETCODE_PLACED,
        FakeMT5.TRADE_RETCODE_DONE_PARTIAL,
        FakeMT5.TRADE_RETCODE_TIMEOUT,
        FakeMT5.TRADE_RETCODE_ORDER_CHANGED,
        FakeMT5.TRADE_RETCODE_LOCKED,
    ):
        result = ICMarketsMT5DemoAdapter(mt5_module=FakeMT5(retcode=code)).execute(request())
        assert result.accepted is False
        assert result.ambiguous is True
