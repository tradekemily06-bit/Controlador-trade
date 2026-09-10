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

    def __init__(self, check_code=0, send_result=True):
        self.check_code = check_code
        self.send_result = send_result
        self.calls = []

    def initialize(self):
        self.calls.append("initialize")
        return True

    def shutdown(self):
        self.calls.append("shutdown")

    def account_info(self):
        self.calls.append("account_info")
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, enabled):
        self.calls.append(("symbol_select", symbol, enabled))
        return True

    def symbol_info_tick(self, symbol):
        self.calls.append(("symbol_info_tick", symbol))
        return SimpleNamespace(ask=100.0, bid=99.0)

    def order_check(self, payload):
        self.calls.append(("order_check", payload))
        return SimpleNamespace(retcode=self.check_code)

    def order_send(self, payload):
        self.calls.append(("order_send", payload))
        if not self.send_result:
            return None
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=123456, deal=654321)

    def last_error(self):
        return (1, "fake error")


def request(mode=ExecutionMode.DEMO, signal=Signal.COMPRA):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=signal,
        amount=0.01,
        duration_seconds=60,
        mode=mode,
        request_id="test-1",
    )


def test_demo_order_checks_before_send_and_confirms():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request())

    assert result.accepted is True
    assert result.external_id == "123456"
    names = [call if isinstance(call, str) else call[0] for call in mt5.calls]
    assert names.index("order_check") < names.index("order_send")


def test_aguardar_never_reaches_mt5():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request(signal=Signal.AGUARDAR))

    assert result.accepted is False
    assert mt5.calls == []


def test_real_mode_is_blocked_before_mt5_access():
    mt5 = FakeMT5()
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request(mode=ExecutionMode.REAL))

    assert result.accepted is False
    assert "somente DEMO" in result.message
    assert mt5.calls == []


def test_order_check_failure_blocks_send():
    mt5 = FakeMT5(check_code=10019)
    adapter = ICMarketsMT5DemoAdapter(mt5_module=mt5)

    result = adapter.execute(request())

    assert result.accepted is False
    assert "order_check" in result.message
    assert not any(
        isinstance(call, tuple) and call[0] == "order_send" for call in mt5.calls
    )
