from __future__ import annotations

import pytest

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.paper import PaperExecutor
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
