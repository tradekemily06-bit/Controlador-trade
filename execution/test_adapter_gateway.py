import pytest
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
    result = gateway_with(adapter).execute(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_capability_is_pinned_to_adapter_instance():
    first = FakeAdapter()
    gateway = gateway_with(first)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    second = FakeAdapter()
    gateway._registry._adapters["fake"] = second
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=capability,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert second.calls == 0


def test_real_dispatch_rejects_overridable_registry_before_dispatch():
    class FlipRegistry(BrokerRegistry):
        pass
    with pytest.raises(ValueError, match="registry inválido"):
        BrokerAdapterGateway(FlipRegistry())


def test_real_dispatch_blocks_adapter_identity_mutation_after_capture():
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    adapter.adapter_id = "different-adapter"
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=capability,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_dispatch_rechecks_mutable_capability_after_availability_identity_type():
    class MutatingAdapter(FakeAdapter):
        def is_available(self):
            self.adapter_id = 123
            return True
    adapter = MutatingAdapter()
    gateway = gateway_with(adapter)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=capability,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_dispatch_rechecks_mutable_supports_real_after_availability():
    class MutatingAdapter(FakeAdapter):
        def is_available(self):
            self.supports_real_execution = False
            return True
    adapter = MutatingAdapter()
    gateway = gateway_with(adapter)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=capability,
        request_id="real-test",
        authorization_id="auth",
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
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=capability,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_dispatch_rejects_overridable_capability_subclass():
    from execution.adapter_gateway import _RealDispatchCapability
    class CapabilityOverride(_RealDispatchCapability):
        @property
        def adapter(self):
            raise AssertionError("capability override must never be trusted")
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    forged = object.__new__(CapabilityOverride)
    object.__setattr__(forged, "_adapter", adapter)
    object.__setattr__(forged, "_adapter_id", "fake-adapter")
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=forged,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert adapter.calls == 0


def test_real_dispatch_rejects_forged_exact_capability_instance():
    from execution.adapter_gateway import _RealDispatchCapability
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    forged = _RealDispatchCapability(adapter, "fake-adapter", "fake", "real-test", "auth")
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"),
        capability=forged,
        request_id="real-test",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert "não emitida pelo gateway" in result.message
    assert adapter.calls == 0


def test_real_dispatch_control_surface_is_not_public():
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gateway = BrokerAdapterGateway(registry)
    assert not hasattr(gateway, "execute_real")
    assert not hasattr(gateway, "real_dispatch_capability")


def test_real_dispatch_rejects_context_reuse_for_different_request():
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    result = gateway._execute_real(
        "fake",
        ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="other-request"),
        capability=capability,
        request_id="other-request",
        authorization_id="auth",
    )
    assert result.accepted is False
    assert "contexto autorizado" in result.message
    assert adapter.calls == 0


def test_real_dispatch_rejects_execution_request_subclass():
    class RequestOverride(ExecutionRequest):
        pass
    adapter = FakeAdapter()
    gateway = gateway_with(adapter)
    capability = gateway._real_dispatch_capability(
        "fake", expected_adapter_id="fake-adapter", request_id="real-test", authorization_id="auth"
    )
    assert capability is not None
    forged_request = RequestOverride(
        "BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="real-test"
    )
    result = gateway._execute_real(
        "fake", forged_request, capability=capability,
        request_id="real-test", authorization_id="auth"
    )
    assert result.accepted is False
    assert adapter.calls == 0
