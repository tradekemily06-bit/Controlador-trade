import pytest

from core.market_context import (
    MarketContext,
    MarketContextEngine,
    MarketDirection,
)


def test_contexto_favoravel():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend_strength=90,
        volatility_quality=80,
        liquidity_quality=90,
        direction=MarketDirection.ALTA,
    )

    assert result.context == MarketContext.FAVORAVEL
    assert result.score >= 70
    assert result.direction == MarketDirection.ALTA


def test_contexto_desfavoravel():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend_strength=10,
        volatility_quality=20,
        liquidity_quality=10,
        direction=MarketDirection.BAIXA,
    )

    assert result.context == MarketContext.DESFAVORAVEL
    assert result.score <= 30
    assert result.direction == MarketDirection.BAIXA


def test_contexto_neutro():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend_strength=50,
        volatility_quality=50,
        liquidity_quality=50,
    )

    assert result.context == MarketContext.NEUTRO
    assert result.score == 50
    assert result.direction == MarketDirection.NEUTRA


@pytest.mark.parametrize(
    "field",
    [
        "trend_strength",
        "volatility_quality",
        "liquidity_quality",
    ],
)
def test_valores_abaixo_de_zero_sao_rejeitados(field):
    engine = MarketContextEngine()

    values = {
        "trend_strength": 50,
        "volatility_quality": 50,
        "liquidity_quality": 50,
    }

    values[field] = -1

    with pytest.raises(ValueError):
        engine.evaluate(**values)


@pytest.mark.parametrize(
    "field",
    [
        "trend_strength",
        "volatility_quality",
        "liquidity_quality",
    ],
)
def test_valores_acima_de_cem_sao_rejeitados(field):
    engine = MarketContextEngine()

    values = {
        "trend_strength": 50,
        "volatility_quality": 50,
        "liquidity_quality": 50,
    }

    values[field] = 101

    with pytest.raises(ValueError):
        engine.evaluate(**values)


@pytest.mark.parametrize(
    "direction",
    [
        MarketDirection.ALTA,
        MarketDirection.BAIXA,
        MarketDirection.NEUTRA,
    ],
)
def test_direcao_e_preservada(direction):
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend_strength=80,
        volatility_quality=80,
        liquidity_quality=80,
        direction=direction,
    )

    assert result.direction == direction


def test_direcao_invalida_e_rejeitada():
    engine = MarketContextEngine()

    with pytest.raises(ValueError):
        engine.evaluate(
            trend_strength=80,
            volatility_quality=80,
            liquidity_quality=80,
            direction="INVALIDA",
        )


def test_volatilidade_baixa_pode_ser_qualidade():
    engine = MarketContextEngine()

    result = engine.evaluate(
        trend_strength=80,
        volatility_quality=90,
        liquidity_quality=90,
    )

    assert result.context == MarketContext.FAVORAVEL


def test_score_nao_define_direcao():
    engine = MarketContextEngine()

    alta = engine.evaluate(
        trend_strength=90,
        volatility_quality=90,
        liquidity_quality=90,
        direction=MarketDirection.ALTA,
    )

    baixa = engine.evaluate(
        trend_strength=90,
        volatility_quality=90,
        liquidity_quality=90,
        direction=MarketDirection.BAIXA,
    )

    assert alta.score == baixa.score
    assert alta.direction == MarketDirection.ALTA
    assert baixa.direction == MarketDirection.BAIXA
