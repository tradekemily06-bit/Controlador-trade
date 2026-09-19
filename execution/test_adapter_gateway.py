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
    return ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO)


def gateway_with(adapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    return BrokerAdapterGateway(registry)


def test_public_adapter_gateway_blocks_direct_real_dispatch():
    adapter = FakeAdapter()
    result = gateway_with(adapter).execute(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL),
    )
    assert result.accepted is False
    assert result.dispatch_attempted is False
    assert adapter.calls == 0


def test_adapter_gateway_checks_availability_before_execution():
    adapter = FakeAdapter(available=False)

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is False
    assert result.dispatch_attempted is False
    assert adapter.calls == 0


def test_adapter_gateway_delegates_only_to_available_adapter():
    adapter = FakeAdapter()

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is True
    assert result.execution is not None
    assert result.execution.external_id == "FAKE-1"
    assert result.dispatch_attempted is True
    assert adapter.calls == 1


def test_adapter_gateway_propagates_adapter_exception_as_uncertain():
    import pytest
    from execution.adapter_gateway import AdapterGatewayError

    adapter = FakeAdapter(error=True)

    with pytest.raises(AdapterGatewayError, match="execução não confirmada"):
        gateway_with(adapter).execute("fake", request())

    assert adapter.calls == 1


def test_adapter_gateway_rejects_invalid_adapter_result():
    adapter = FakeAdapter(result="invalid")

    result = gateway_with(adapter).execute("fake", request())

    assert result.accepted is False
    assert result.execution is None
    assert result.dispatch_attempted is True


def test_adapter_gateway_unknown_broker_does_not_execute():
    registry = BrokerRegistry()
    gateway = BrokerAdapterGateway(registry)

    result = gateway.execute("missing", request())

    assert result.accepted is False
    assert result.execution is None
    assert result.dispatch_attempted is False


def test_adapter_gateway_rejects_malformed_public_request_without_touching_adapter():
    adapter = FakeAdapter()
    result = gateway_with(adapter).execute("fake", None)
    assert result.accepted is False
    assert result.dispatch_attempted is False
    assert adapter.calls == 0


def test_adapter_gateway_rejects_forged_real_capability():
    adapter = FakeAdapter()
    from execution.ports import ExecutionRequest
    from core.models import Signal
    real_request = ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)

    import pytest
    with pytest.raises(PermissionError, match="capacidade de despacho REAL inválida"):
        gateway_with(adapter).execute_real("fake", real_request, capability=object())

    assert adapter.calls == 0
