import math

import pytest

from core.runtime_config import RuntimeConfig
from execution.ports import ExecutionMode


def valid_config():
    return RuntimeConfig(
        symbol="EURUSD",
        timeframe="5m",
        amount=10.0,
        duration_seconds=60,
    )


def test_valid_config_is_immutable_and_defaults_to_demo():
    config = valid_config()
    assert config.mode is ExecutionMode.DEMO
    assert config.symbol == "EURUSD"
    with pytest.raises(Exception):
        config.amount = 20.0


def test_invalid_required_values_are_rejected():
    with pytest.raises(ValueError):
        RuntimeConfig("", "5m", 10, 60)
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "", 10, 60)
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "5m", 0, 60)
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "5m", 10, 0)


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_amount_is_rejected(amount):
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "5m", amount, 60)


def test_real_mode_is_always_rejected():
    with pytest.raises(ValueError, match="REAL"):
        RuntimeConfig("EURUSD", "5m", 10, 60, mode=ExecutionMode.REAL)


def test_boolean_numeric_values_are_rejected():
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "5m", True, 60)
    with pytest.raises(ValueError):
        RuntimeConfig("EURUSD", "5m", 10, True)


def test_paths_are_normalized_and_exposed():
    config = RuntimeConfig("EURUSD", "5m", 10, 60, memory_path="state/memory.json")
    assert config.memory_path.name == "memory.json"
    assert config.paths() == (config.memory_path,)
