from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig, MT5AdapterError
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_TIMEOUT = 10012

    def __init__(self, send_retcode):
        self.send_retcode = send_retcode
        self.shutdown_calls = 0

    def initialize(self): return True
    def shutdown(self): self.shutdown_calls += 1
    def account_info(self): return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)
    def symbol_select(self, symbol, enabled): return True
    def symbol_info(self, symbol): return SimpleNamespace(volume_min=0.01, volume_max=10.0, volume_step=0.01)
    def symbol_info_tick(self, symbol): return SimpleNamespace(ask=100.0, bid=99.0)
    def order_check(self, payload): return SimpleNamespace(retcode=0)
    def order_send(self, payload): return SimpleNamespace(retcode=self.send_retcode, order=123, deal=456)
    def last_error(self): return (0, "ok")


def req():
    return ExecutionRequest("TEST", Signal.COMPRA, 0.01, 60, ExecutionMode.DEMO, "stage3-ambiguous")


def test_ambiguous_mt5_outcomes_raise_uncertain_boundary_error():
    for code in (10008, 10010, 10012):
        mt5 = FakeMT5(code)
        adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol="TEST"), mt5_module=mt5)
        try:
            adapter.execute(req())
        except MT5AdapterError:
            pass
        else:
            raise AssertionError(f"retcode {code} must remain uncertain")
        assert mt5.shutdown_calls == 1
