from core.models import Signal
from execution.p123_broker_order import BrokerOrderRequest, BrokerOrderResult
from execution.p127_ctrader_demo import CTraderDemoAdapter, CTRADER_DEMO_ENDPOINT
from execution.ports import ExecutionMode, ExecutionRequest


class FakeDemoTransport:
    endpoint = CTRADER_DEMO_ENDPOINT

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


def test_demo_adapter_rejects_non_demo_transport_endpoint():
    class LiveTransport(FakeDemoTransport):
        endpoint = "live.ctraderapi.com:5035"

    try:
        CTraderDemoAdapter(LiveTransport())
    except ValueError as exc:
        assert "endpoint DEMO" in str(exc)
    else:
        raise AssertionError("transport live não pode entrar no adapter DEMO")


def test_demo_adapter_rejects_invalid_order_before_transport(tmp_path=None):
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)

    result = adapter.execute(ExecutionRequest("EURUSD", Signal.COMPRA, 0, 60, ExecutionMode.DEMO, "bad-amount"))

    assert result.accepted is False
    assert result.uncertain is False
    assert transport.orders == []


def test_demo_adapter_marks_transport_exception_uncertain():
    class FailingTransport(FakeDemoTransport):
        def place_market_order(self, order):
            self.orders.append(order)
            raise TimeoutError("transport timeout")

    result = CTraderDemoAdapter(FailingTransport()).execute(request())
    assert result.accepted is False
    assert result.uncertain is True


def test_demo_adapter_marks_accepted_without_external_id_uncertain():
    transport = FakeDemoTransport(result=BrokerOrderResult(True, "accepted", None))
    result = CTraderDemoAdapter(transport).execute(request())
    assert result.accepted is False
    assert result.uncertain is True


def test_ctrader_order_contract_carries_deterministic_recovery_correlation():
    transport = FakeDemoTransport()
    adapter = CTraderDemoAdapter(transport)
    request = ExecutionRequest("EURUSD", Signal.COMPRA, 1.0, 60, ExecutionMode.DEMO, request_id="req-correlation")

    result = adapter.execute(request)

    assert result.accepted is True
    assert transport.orders[0].correlation == adapter.correlation_for(request)
    assert transport.orders[0].correlation.startswith("CTD-")
    assert len(transport.orders[0].correlation) == 36
