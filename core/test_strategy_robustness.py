from math import inf, nan

import pytest

from core.models import Signal
from core.strategy_engine import StrategyEngine, StrategyInput


def make_input(**overrides):
    values = {
        "trend": 100.0,
        "pressure": 100.0,
        "structure": 100.0,
        "rejection": 100.0,
        "volume": 100.0,
        "confirmation": 100.0,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "TEST",
        "timeframe": "5m",
    }
    values.update(overrides)
    return StrategyInput(**values)


@pytest.mark.parametrize("field", [
    "trend", "pressure", "structure", "rejection", "volume", "confirmation"
])
def test_strategy_rejects_boolean_components(field):
    with pytest.raises(ValueError):
        StrategyEngine().evaluate(make_input(**{field: True}))


@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_strategy_rejects_non_finite_score_components(value):
    with pytest.raises(ValueError):
        StrategyEngine().evaluate(make_input(trend=value))


def test_boundary_score_70_is_buy():
    # 20% trend + 20% pressure + 20% structure + 15% rejection
    # + 10% volume + 15% confirmation = 70.
    result = StrategyEngine().evaluate(
        make_input(
            trend=70.0,
            pressure=70.0,
            structure=70.0,
            rejection=70.0,
            volume=70.0,
            confirmation=70.0,
        )
    )
    assert result.score == 70.0
    assert result.signal == Signal.COMPRA


def test_boundary_score_30_is_sell():
    result = StrategyEngine().evaluate(
        make_input(
            trend=30.0,
            pressure=30.0,
            structure=30.0,
            rejection=30.0,
            volume=30.0,
            confirmation=30.0,
        )
    )
    assert result.score == 30.0
    assert result.signal == Signal.VENDA


def test_middle_score_is_wait():
    result = StrategyEngine().evaluate(
        make_input(
            trend=50.0,
            pressure=50.0,
            structure=50.0,
            rejection=50.0,
            volume=50.0,
            confirmation=50.0,
        )
    )
    assert result.score == 50.0
    assert result.signal == Signal.AGUARDAR


def test_filter_block_always_overrides_actionable_score():
    result = StrategyEngine().evaluate(make_input(filters_ok=False))

    assert result.score == 100.0
    assert result.signal == Signal.AGUARDAR
    assert result.confirmed is True
    assert "Filtros" in result.reason


def test_confirmation_block_overrides_high_score():
    result = StrategyEngine().evaluate(make_input(confirmed=False))

    assert result.score == 100.0
    assert result.signal == Signal.AGUARDAR
    assert result.confirmed is False


def test_invalid_filter_value_is_not_silently_coerced():
    with pytest.raises(ValueError):
        StrategyEngine().evaluate(make_input(filters_ok=None))


def test_metadata_is_preserved_without_affecting_score():
    result = StrategyEngine().evaluate(
        make_input(symbol="BTCUSD", timeframe="1m")
    )

    assert result.symbol == "BTCUSD"
    assert result.timeframe == "1m"
    assert result.score == 100.0


def test_extreme_valid_inputs_remain_deterministic():
    engine = StrategyEngine()
    first = engine.evaluate(make_input())
    second = engine.evaluate(make_input())

    assert first == second
