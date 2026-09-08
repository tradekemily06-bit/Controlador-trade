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


def test_strategy_engine_generates_buy_from_strong_score():
    result = StrategyEngine().evaluate(make_input())

    assert result.signal == Signal.COMPRA
    assert result.score == 100.0
    assert result.confirmed is True
    assert result.symbol == "TEST"
    assert result.timeframe == "5m"


def test_strategy_engine_generates_sell_from_weak_score():
    result = StrategyEngine().evaluate(
        make_input(
            trend=0.0,
            pressure=0.0,
            structure=0.0,
            rejection=0.0,
            volume=0.0,
            confirmation=0.0,
        )
    )

    assert result.signal == Signal.VENDA
    assert result.score == 0.0


def test_strategy_engine_awaits_confirmation():
    result = StrategyEngine().evaluate(make_input(confirmed=False))

    assert result.signal == Signal.AGUARDAR
    assert result.confirmed is False


def test_strategy_engine_respects_filters():
    result = StrategyEngine().evaluate(make_input(filters_ok=False))

    assert result.signal == Signal.AGUARDAR
    assert "Filtros" in result.reason


@pytest.mark.parametrize("field", [
    "trend",
    "pressure",
    "structure",
    "rejection",
    "volume",
    "confirmation",
])
def test_strategy_engine_rejects_non_finite_values(field):
    result = make_input(**{field: nan})

    with pytest.raises(ValueError):
        StrategyEngine().evaluate(result)


@pytest.mark.parametrize("field", [
    "trend",
    "pressure",
    "structure",
    "rejection",
    "volume",
    "confirmation",
])
def test_strategy_engine_rejects_infinite_values(field):
    result = make_input(**{field: inf})

    with pytest.raises(ValueError):
        StrategyEngine().evaluate(result)


@pytest.mark.parametrize("field", [
    "trend",
    "pressure",
    "structure",
    "rejection",
    "volume",
    "confirmation",
])
def test_strategy_engine_rejects_out_of_range_values(field):
    with pytest.raises(ValueError):
        StrategyEngine().evaluate(make_input(**{field: 100.1}))

    with pytest.raises(ValueError):
        StrategyEngine().evaluate(make_input(**{field: -0.1}))
