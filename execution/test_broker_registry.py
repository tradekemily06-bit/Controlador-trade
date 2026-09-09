import pytest

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionResult


class FakeAdapter:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(accepted=True, message="ok", external_id="FAKE-1")

    def is_available(self):
        return self.available


def test_registry_registers_and_normalizes_name():
    registry = BrokerRegistry()
    adapter = FakeAdapter()

    registry.register("  TestBroker ", adapter)

    assert registry.names() == ("testbroker",)
    assert registry.get("TESTBROKER") is adapter
    assert registry.is_available("testbroker") is True


def test_registry_rejects_duplicate_name():
    registry = BrokerRegistry()
    registry.register("broker", FakeAdapter())

    with pytest.raises(BrokerRegistryError):
        registry.register("BROKER", FakeAdapter())


def test_registry_requires_adapter_contract():
    registry = BrokerRegistry()

    with pytest.raises(BrokerRegistryError):
        registry.register("broken", object())


def test_registry_unknown_adapter_fails_closed():
    registry = BrokerRegistry()

    with pytest.raises(BrokerRegistryError):
        registry.get("unknown")


def test_registry_reports_unavailable_adapter_without_executing():
    registry = BrokerRegistry()
    adapter = FakeAdapter(available=False)
    registry.register("paper", adapter)

    assert registry.is_available("paper") is False
    assert adapter.calls == 0


def test_registry_info_is_read_only_snapshot():
    registry = BrokerRegistry()
    registry.register("paper", FakeAdapter())

    info = registry.info()

    assert info[0].name == "paper"
    assert info[0].available is True
    assert isinstance(info, tuple)
