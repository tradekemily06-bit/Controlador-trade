from types import SimpleNamespace

from core.models import Signal
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionAction, ExecutionMode, ExecutionRequest


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self, *, demo=True, order_ok=True, send_ok=True, external_id=True):
        self.demo = demo
        self.order_ok = order_ok
        self.send_ok = send_ok
        self.external_id = external_id
        self.shutdown_calls = 0
        self.sent = []
        self.positions = [SimpleNamespace(ticket=777, symbol="EURUSD", volume=0.01, type=self.POSITION_TYPE_BUY, magic=2609001)]

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_calls += 1

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO if self.demo else 0)

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(ask=1.1002, bid=1.1000)

    def positions_get(self, symbol=None):
        return tuple(p for p in self.positions if symbol is None or p.symbol == symbol)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0 if self.order_ok else 10030)

    def order_send(self, payload):
        self.sent.append(payload)
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE if self.send_ok else 10006,
            order=123456 if self.external_id else None,
            deal=654321 if self.external_id else None,
        )

    def last_error(self):
        return (0, "ok")


def request(signal=Signal.COMPRA, mode=ExecutionMode.DEMO, amount=0.01):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=signal,
        amount=amount,
        duration_seconds=60,
        mode=mode,
        request_id="test-1",
    )


def test_demo_buy_is_sent_after_order_check():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is True
    assert result.external_id == "123456"
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_BUY
    assert fake.sent[0]["volume"] == 0.01
    assert fake.shutdown_calls == 1


def test_real_request_is_blocked_before_mt5_call():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(
        request(mode=ExecutionMode.REAL)
    )

    assert result.accepted is False
    assert fake.sent == []


def test_non_demo_account_is_blocked():
    fake = FakeMT5(demo=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_aguardar_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(Signal.AGUARDAR))

    assert result.accepted is False
    assert fake.sent == []


def test_order_check_blocks_send():
    fake = FakeMT5(order_ok=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_volume_below_symbol_minimum_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(amount=0.001))

    assert result.accepted is False
    assert fake.sent == []


def test_volume_not_aligned_to_symbol_step_is_blocked():
    fake = FakeMT5()
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request(amount=0.015))

    assert result.accepted is False
    assert fake.sent == []


def test_invalid_price_is_blocked():
    fake = FakeMT5()
    fake.symbol_info_tick = lambda symbol: SimpleNamespace(ask=0.0, bid=1.1000)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert fake.sent == []


def test_missing_external_id_is_not_confirmed():
    fake = FakeMT5(external_id=False)
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(request())

    assert result.accepted is False
    assert result.external_id is None
    assert len(fake.sent) == 1

def test_demo_close_uses_shared_adapter_boundary():
    fake = FakeMT5()
    close_request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.VENDA,
        amount=0.01,
        duration_seconds=1,
        mode=ExecutionMode.DEMO,
        request_id="close-1",
        action=ExecutionAction.CLOSE,
        position_id=777,
    )
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(close_request)
    assert result.accepted is True
    assert fake.sent[0]["position"] == 777
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_SELL


def test_demo_close_requires_exactly_one_controlador_position():
    fake = FakeMT5()
    fake.positions = []
    close_request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.VENDA,
        amount=0.01,
        duration_seconds=1,
        mode=ExecutionMode.DEMO,
        request_id="close-2",
        action=ExecutionAction.CLOSE,
        position_id=777,
    )
    result = ICMarketsMT5DemoAdapter(mt5_module=fake).execute(close_request)
    assert result.accepted is False
    assert fake.sent == []
