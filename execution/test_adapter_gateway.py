from execution.adapter_gateway import BrokerAdapterGateway
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


def request():
    return ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def gateway_with(adapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    return BrokerAdapterGateway(registry)


def test_adapter_gateway_checks_availability_before_execution():
    adapter = FakeAdapter(available=False)

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is False
    assert adapter.calls == 0


def test_adapter_gateway_delegates_only_to_available_adapter():
    adapter = FakeAdapter()

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is True
    assert result.execution is not None
    assert result.execution.external_id == "FAKE-1"
    assert adapter.calls == 1


def test_adapter_gateway_handles_adapter_exception_fail_closed():
    adapter = FakeAdapter(error=True)

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is False
    assert result.execution is None
    assert adapter.calls == 1


def test_adapter_gateway_rejects_invalid_adapter_result():
    adapter = FakeAdapter(result="invalid")

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is False
    assert result.execution is None


def test_adapter_gateway_unknown_broker_does_not_execute():
    registry = BrokerRegistry()
    gateway = BrokerAdapterGateway(registry)

    result = gateway.execute("missing", request())

    assert result.accepted is False
    assert result.execution is None
