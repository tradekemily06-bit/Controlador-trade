from __future__ import annotations

from execution.outcome_registry import ExternalOutcomeRegistry, OutcomeRegistryError


class FakeOutcome:
    def close_and_observe(self, request_id):
        raise AssertionError("not called")

    def observe_closed_position(self, request_id):
        raise AssertionError("not called")


def test_registry_accepts_arbitrary_outcome_adapter() -> None:
    registry = ExternalOutcomeRegistry()
    adapter = FakeOutcome()
    registry.register("future-broker-platform-bridge", adapter)
    assert registry.get("future-broker-platform-bridge") is adapter
    assert registry.names() == ("future-broker-platform-bridge",)


def test_registry_rejects_duplicate_name() -> None:
    registry = ExternalOutcomeRegistry()
    registry.register("future", FakeOutcome())
    try:
        registry.register("future", FakeOutcome())
    except OutcomeRegistryError:
        return
    raise AssertionError("duplicate outcome adapter should be rejected")
