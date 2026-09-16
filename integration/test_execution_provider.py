from __future__ import annotations

import pytest

from execution.demo_broker_port import DemoBrokerExecutionPort
from execution.paper import PaperExecutor
from integration.execution_provider import (
    ExecutionProviderConfigurationError,
    build_demo_execution_port,
)


def test_paper_is_safe_default():
    executor = build_demo_execution_port()
    assert isinstance(executor, PaperExecutor)


def test_ic_markets_mt5_demo_keeps_adapter_private():
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    assert isinstance(executor, DemoBrokerExecutionPort)
    assert not executor.__class__.__module__.startswith("integration")
    assert not hasattr(executor, "adapter")


def test_unknown_provider_fails_closed():
    with pytest.raises(ExecutionProviderConfigurationError):
        build_demo_execution_port("unknown-provider")
