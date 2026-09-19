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


def test_demo_adapter_rejects_non_boolean_transport_availability_fail_closed():
    transport = FakeDemoTransport(available="yes")
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(request())

    assert result.accepted is False
    assert "indisponível" in result.message
    assert transport.orders == []


def test_demo_adapter_converts_transport_health_exception_to_rejection():
    class BrokenHealthTransport(FakeDemoTransport):
        def is_available(self):
            raise RuntimeError("health down")

    transport = BrokenHealthTransport()
    result = CTraderDemoAdapter(transport).execute(request())

    assert result.accepted is False
    assert transport.orders == []


def test_demo_adapter_rejects_request_subclass_before_transport():
    class RequestOverride(ExecutionRequest):
        pass

    transport = FakeDemoTransport()
    forged = RequestOverride("EURUSD", Signal.COMPRA, 10, 60, ExecutionMode.DEMO, "req-127")
    result = CTraderDemoAdapter(transport).execute(forged)

    assert result.accepted is False
    assert transport.orders == []


def test_demo_adapter_converts_transport_order_exception_to_rejection():
    class BrokenOrderTransport(FakeDemoTransport):
        def place_market_order(self, order):
            self.orders.append(order)
            raise RuntimeError("transport down")

    transport = BrokenOrderTransport()
    result = CTraderDemoAdapter(transport).execute(request())

    assert result.accepted is False
    assert "falha cTrader DEMO" in result.message
    assert len(transport.orders) == 1


def test_demo_adapter_rejects_malformed_broker_result():
    transport = FakeDemoTransport(result="invalid")
    result = CTraderDemoAdapter(transport).execute(request())

    assert result.accepted is False
    assert transport.orders


def test_ctrader_demo_rejects_noncanonical_request_id_before_transport():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)
    forged = request()
    forged = ExecutionRequest(
        forged.symbol,
        forged.signal,
        forged.amount,
        forged.duration_seconds,
        forged.mode,
        " ctrader-1 ",
    )

    result = adapter.execute(forged)

    assert result.accepted is False
    assert "request_id" in result.message
    assert transport.orders == []
