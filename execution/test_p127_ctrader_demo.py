from core.models import Signal
from execution.p123_broker_order import BrokerOrderRequest, BrokerOrderResult
from execution.p127_ctrader_demo import CTraderDemoAdapter, CTRADER_DEMO_ENDPOINT
from execution.ports import ExecutionMode, ExecutionRequest


class FakeDemoTransport:
    def __init__(self, available=True, result=None):
        self.available = available
        self.result = result or BrokerOrderResult(True, "accepted", "demo-123")
        self.orders = []

    def is_available(self):
        return self.available

    def place_market_order(self, order: BrokerOrderRequest):
        self.orders.append(order)
        return self.result


def request(signal=Signal.COMPRA, mode=ExecutionMode.DEMO, request_id="req-127"):
    return ExecutionRequest("EURUSD", signal, 10, 60, mode, request_id)


def test_demo_adapter_accepts_demo_result_and_preserves_external_id():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request())

    assert adapter.endpoint == CTRADER_DEMO_ENDPOINT
    assert result.accepted is True
    assert result.external_id == "demo-123"
    assert transport.orders[0].request_id == "req-127"
    assert transport.orders[0].side.value == "BUY"


def test_demo_adapter_rejects_real_mode():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request(mode=ExecutionMode.REAL))

    assert result.accepted is False
    assert transport.orders == []


def test_demo_adapter_does_not_send_without_request_id():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request(request_id=None))

    assert result.accepted is False
    assert transport.orders == []


def test_demo_adapter_does_not_send_when_unavailable():
    transport = FakeDemoTransport(available=False)
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request())

    assert result.accepted is False
    assert transport.orders == []


def test_demo_adapter_does_not_send_aguardar():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request(signal=Signal.AGUARDAR))

    assert result.accepted is False
    assert transport.orders == []
