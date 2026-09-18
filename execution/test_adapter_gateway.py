from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from core.models import Signal


class FakeAdapter:
    supports_real_execution = True
    adapter_id = "fake-adapter"

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


def test_adapter_gateway_rejects_direct_real_dispatch():
    adapter = FakeAdapter()
    result = gateway_with(adapter).execute("fake", ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL))
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_capability_is_pinned_to_adapter_instance():
    first = FakeAdapter()
    gateway = gateway_with(first)
    capability = gateway.real_dispatch_capability("fake", expected_adapter_id="fake-adapter")
    assert capability is not None
    second = FakeAdapter()
    gateway._registry._adapters["fake"] = second
    result = gateway.execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL),
        capability=capability,
    )
    assert result.accepted is False
    assert second.calls == 0



def test_real_dispatch_blocks_registry_toctou_before_adapter_execute():
    first = FakeAdapter()
    second = FakeAdapter()

    class FlipRegistry(BrokerRegistry):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def get(self, name):
            self.calls += 1
            return first if self.calls <= 2 else second

    registry = FlipRegistry()
    gateway = BrokerAdapterGateway(registry)
    capability = gateway.real_dispatch_capability("fake", expected_adapter_id="fake-adapter")
    assert capability is not None

    result = gateway.execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL),
        capability=capability,
    )

    assert result.accepted is False
    assert first.calls == 0
    assert second.calls == 0



def test_real_dispatch_blocks_adapter_identity_mutation_after_capture():
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    capability = gateway.real_dispatch_capability("fake", expected_adapter_id="fake-adapter")
    assert capability is not None

    adapter.adapter_id = "different-adapter"
    result = gateway.execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL),
        capability=capability,
    )

    assert result.accepted is False
    assert adapter.calls == 0



def test_real_dispatch_rechecks_mutable_capability_after_availability():
    class MutatingAdapter(FakeAdapter):
        def is_available(self):
            self.adapter_id = "changed-during-availability"
            return True

    adapter = MutatingAdapter()
    gateway = gateway_with(adapter)
    capability = gateway.real_dispatch_capability("fake", expected_adapter_id="fake-adapter")
    assert capability is not None

    result = gateway.execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL),
        capability=capability,
    )

    assert result.accepted is False
    assert adapter.calls == 0
