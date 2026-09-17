from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 1
    TRADE_ACTION_DEAL = 10
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 20
    ORDER_FILLING_IOC = 30
    TRADE_RETCODE_DONE = 100

    def __init__(self, *, demo=True, order_check_retcode=0, external_id=123):
        self.demo = demo
        self.order_check_retcode = order_check_retcode
        self.external_id = external_id
        self.initialized = 0
        self.shutdowns = 0
        self.order_checks = 0
        self.order_sends = 0

    def initialize(self):
        self.initialized += 1
        return True

    def shutdown(self):
        self.shutdowns += 1

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 999)

    def symbol_select(self, symbol, enabled):
        return enabled

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=10.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=100.0, bid=99.0)

    def order_check(self, payload):
        self.order_checks += 1
        return SimpleNamespace(retcode=self.order_check_retcode)

    def order_send(self, payload):
        self.order_sends += 1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=self.external_id, deal=None)

    def last_error(self):
        return (0, "ok")


def _request(mode=ExecutionMode.DEMO, signal=Signal.COMPRA):
    return ExecutionRequest("EURUSD", signal, 0.01, 60, mode, request_id="stage3-test")


def test_stage3_mt5_rejects_real_before_terminal_access():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(), mt5_module=mt5)
    result = adapter.execute(_request(mode=ExecutionMode.REAL))
    assert not result.accepted
    assert mt5.initialized == 0


def test_stage3_mt5_rejects_aguardar_before_terminal_access():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    result = adapter.execute(_request(signal=Signal.AGUARDAR))
    assert not result.accepted
    assert mt5.initialized == 0


def test_stage3_mt5_requires_demo_account():
    mt5 = FakeMT5(demo=False)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    result = adapter.execute(_request())
    assert not result.accepted
    assert mt5.order_sends == 0


def test_stage3_mt5_order_check_precedes_send():
    mt5 = FakeMT5(order_check_retcode=1001)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    result = adapter.execute(_request())
    assert not result.accepted
    assert mt5.order_checks == 1
    assert mt5.order_sends == 0


def test_stage3_mt5_confirmed_demo_execution_requires_external_id():
    mt5 = FakeMT5(external_id=None)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)
    with pytest.raises(MT5AdapterError, match="identificador externo"):
        adapter.execute(_request())
    assert mt5.order_sends == 1
