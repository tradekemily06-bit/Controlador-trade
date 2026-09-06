import pytest

from core.market_context import (
    MarketContext,
    MarketContextEngine,
)


def test_contexto_favoravel():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend=90,
        volatility=80,
        liquidity=90,
    )

    assert result.context == MarketContext.FAVORAVEL
    assert result.score >= 70


def test_contexto_desfavoravel():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend=10,
        volatility=20,
        liquidity=10,
    )

    assert result.context == MarketContext.DESFAVORAVEL
    assert result.score <= 30


def test_contexto_neutro():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend=50,
        volatility=50,
        liquidity=50,
    )

    assert result.context == MarketContext.NEUTRO
    assert result.score == 50


@pytest.mark.parametrize(
    "field",
    ["trend", "volatility", "liquidity"],
)
def test_valores_abaixo_de_zero_sao_rejeitados(field):
    engine = MarketContextEngine()

    values = {
        "trend": 50,
        "volatility": 50,
        "liquidity": 50,
    }
    values[field] = -1

    with pytest.raises(ValueError):
        engine.evaluate(**values)


@pytest.mark.parametrize(
    "field",
    ["trend", "volatility", "liquidity"],
)
def test_valores_acima_de_cem_sao_rejeitados(field):
    engine = MarketContextEngine()

    values = {
        "trend": 50,
        "volatility": 50,
        "liquidity": 50,
    }
    values[field] = 101

    with pytest.raises(ValueError):
        engine.evaluate(**values)
