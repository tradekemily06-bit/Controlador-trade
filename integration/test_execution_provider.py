from __future__ import annotations

import pytest

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.paper import PaperExecutor
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionResult
from integration.execution_provider import (
    ExecutionProviderConfigurationError,
    build_demo_execution_port,
)


def test_paper_is_safe_default():
    executor = build_demo_execution_port()
    assert isinstance(executor, PaperExecutor)


def test_ic_markets_mt5_demo_requires_explicit_provider():
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    assert isinstance(executor, ICMarketsMT5DemoAdapter)
    assert executor.config.symbol == "EURUSD"


def test_unknown_provider_fails_closed():
    with pytest.raises(ExecutionProviderConfigurationError):
        build_demo_execution_port("unknown-provider")


class ExternalDemoAdapter:
    def execute(self, request):
        return ExecutionResult(accepted=True, message="external demo", external_id="EXT-1")

    def is_available(self):
        return True


def test_external_registry_can_supply_new_demo_adapter_without_factory_change():
    registry = BrokerRegistry()
    registry.register("future_broker_platform", ExternalDemoAdapter())

    executor = build_demo_execution_port(
        "future_broker_platform",
        registry=registry,
    )

    assert executor is registry.get("future_broker_platform")
