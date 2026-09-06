import pytest

from core.filters import passes_filters
from core.scoring import calculate_score


def test_score_normalizado():
    score = calculate_score(
        trend=100,
        pressure=100,
        structure=100,
        rejection=100,
        volume=100,
        confirmation=100,
    )
    assert score == 100.0


def test_score_minimo():
    score = calculate_score(
        trend=0,
        pressure=0,
        structure=0,
        rejection=0,
        volume=0,
        confirmation=0,
    )
    assert score == 0.0


def test_score_limitado():
    assert calculate_score(
        trend=200,
        pressure=200,
        structure=200,
        rejection=200,
        volume=200,
        confirmation=200,
    ) == 100.0

    assert calculate_score(
        trend=-100,
        pressure=-100,
        structure=-100,
        rejection=-100,
        volume=-100,
        confirmation=-100,
    ) == 0.0


def test_score_rejeita_valor_nao_numerico():
    with pytest.raises(ValueError):
        calculate_score(trend="100")


def test_filtros_aprovam_compra_forte():
    assert passes_filters(
        market_open=True,
        data_ok=True,
        risk_ok=True,
        score=80,
        confirmed=True,
    )


def test_filtros_aprovam_venda_forte():
    assert passes_filters(
        market_open=True,
        data_ok=True,
        risk_ok=True,
        score=20,
        confirmed=True,
    )


def test_filtros_rejeitam_score_fraco():
    assert not passes_filters(
        market_open=True,
        data_ok=True,
        risk_ok=True,
        score=50,
        confirmed=True,
    )


def test_filtros_rejeitam_sem_confirmacao():
    assert not passes_filters(
        market_open=True,
        data_ok=True,
        risk_ok=True,
        score=90,
        confirmed=False,
    )


def test_filtros_rejeitam_dados_invalidos():
    assert not passes_filters(
        market_open=True,
        data_ok=False,
        risk_ok=True,
        score=90,
        confirmed=True,
    )


def test_filtros_rejeitam_risco():
    assert not passes_filters(
        market_open=True,
        data_ok=True,
        risk_ok=False,
        score=90,
        confirmed=True,
    )


def test_filtros_rejeitam_mercado_fechado():
    assert not passes_filters(
        market_open=False,
        data_ok=True,
        risk_ok=True,
        score=90,
        confirmed=True,
    )
