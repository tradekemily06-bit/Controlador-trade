from execution.adapter_gateway import BrokerAdapterGateway, _REAL_ADAPTER_GATEWAY_CAPABILITY
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from core.models import Signal


class FakeAdapter:
    def __init__(self, available=True, result=None, error=False):
        self.available = available
        self.result = result or ExecutionResult(True, "ok", "FAKE-1")
        self.error = error
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        if self.error:
            raise RuntimeError("falha simulada")
        return self.result


def request(mode=ExecutionMode.REAL):
    return ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, mode)


def gateway_with(adapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    return BrokerAdapterGateway(registry)


def real_gateway_execute(gateway, broker, req):
    return gateway.execute_from_real_gateway(broker, req, capability=_REAL_ADAPTER_GATEWAY_CAPABILITY)


def test_adapter_gateway_public_execute_cannot_dispatch_real():
    adapter = FakeAdapter()
    result = gateway_with(adapter).execute("fake", request())
    assert result.accepted is False
    assert result.uncertain is False
    assert adapter.calls == 0


def test_adapter_gateway_rejects_invalid_real_capability_without_touching_adapter():
    adapter = FakeAdapter()
    result = gateway_with(adapter).execute_from_real_gateway("fake", request(), capability=object())
    assert result.accepted is False
    assert result.uncertain is False
    assert adapter.calls == 0


def test_adapter_gateway_checks_availability_before_execution():
    adapter = FakeAdapter(available=False)
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is False
    assert adapter.calls == 0


def test_adapter_gateway_rejects_non_boolean_availability():
    adapter = FakeAdapter(available=1)
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is False
    assert adapter.calls == 0


def test_adapter_gateway_delegates_only_to_available_adapter():
    adapter = FakeAdapter()
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is True
    assert result.uncertain is False
    assert result.execution is not None
    assert result.execution.external_id == "FAKE-1"
    assert adapter.calls == 1


def test_adapter_gateway_preserves_adapter_exception_as_uncertain():
    adapter = FakeAdapter(error=True)
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is True
    assert result.execution is None
    assert adapter.calls == 1


def test_adapter_gateway_marks_invalid_adapter_result_uncertain():
    adapter = FakeAdapter(result="invalid")
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is True
    assert result.execution is None


def test_adapter_gateway_marks_non_boolean_acceptance_uncertain():
    adapter = FakeAdapter(result=ExecutionResult(1, "ok", "FAKE-1"))
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is True
    assert result.execution is None
    assert adapter.calls == 1


def test_adapter_gateway_marks_non_string_message_uncertain():
    adapter = FakeAdapter(result=ExecutionResult(True, 123, "FAKE-1"))
    result = real_gateway_execute(gateway_with(adapter), "fake", request())
    assert result.accepted is False
    assert result.uncertain is True
    assert result.execution is None
    assert adapter.calls == 1


def test_adapter_gateway_unknown_broker_does_not_execute():
    registry = BrokerRegistry()
    gateway = BrokerAdapterGateway(registry)
    result = real_gateway_execute(gateway, "missing", request())
    assert result.accepted is False
    assert result.uncertain is False
    assert result.execution is None


def test_adapter_gateway_rejects_demo_without_touching_adapter():
    adapter = FakeAdapter()
    result = real_gateway_execute(gateway_with(adapter), "fake", request(ExecutionMode.DEMO))
    assert result.accepted is False
    assert result.uncertain is False
    assert result.execution is None
    assert adapter.calls == 0
