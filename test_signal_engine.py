from core.models import Signal
from core.signal_engine import SignalEngine


def test_aguarda_sem_confirmacao():
    result = SignalEngine().evaluate(
        score=90,
        confirmed=False,
    )
    assert result.signal == Signal.AGUARDAR


def test_compra_com_score_forte():
    result = SignalEngine().evaluate(
        score=80,
        confirmed=True,
    )
    assert result.signal == Signal.COMPRA


def test_venda_com_score_forte():
    result = SignalEngine().evaluate(
        score=20,
        confirmed=True,
    )
    assert result.signal == Signal.VENDA


def test_aguarda_com_score_intermediario():
    result = SignalEngine().evaluate(
        score=50,
        confirmed=True,
    )
    assert result.signal == Signal.AGUARDAR


def test_filtro_bloqueia_compra():
    result = SignalEngine().evaluate(
        score=90,
        confirmed=True,
        filters_ok=False,
    )
    assert result.signal == Signal.AGUARDAR
    assert "Filtros" in result.reason


def test_filtro_bloqueia_venda():
    result = SignalEngine().evaluate(
        score=10,
        confirmed=True,
        filters_ok=False,
    )
    assert result.signal == Signal.AGUARDAR


def test_preserva_contexto():
    result = SignalEngine().evaluate(
        score=80,
        confirmed=True,
        symbol="EURUSD",
        timeframe="5m",
    )

    assert result.symbol == "EURUSD"
    assert result.timeframe == "5m"


def test_confirmacao_falsa_bloqueia_score_alto():
    result = SignalEngine().evaluate(
        score=100,
        confirmed=False,
    )

    assert result.signal == Signal.AGUARDAR
