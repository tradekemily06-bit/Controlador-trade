from math import inf, nan

from core.models import Signal
from core.signal_engine import SignalEngine


def test_buy_at_threshold():
    result = SignalEngine().evaluate(score=70, confirmed=True)

    assert result.signal is Signal.COMPRA
    assert result.confirmed is True


def test_sell_at_threshold():
    result = SignalEngine().evaluate(score=30, confirmed=True)

    assert result.signal is Signal.VENDA
    assert result.confirmed is True


def test_middle_score_waits():
    result = SignalEngine().evaluate(score=50, confirmed=True)

    assert result.signal is Signal.AGUARDAR


def test_unconfirmed_signal_waits():
    result = SignalEngine().evaluate(score=90, confirmed=False)

    assert result.signal is Signal.AGUARDAR
    assert result.confirmed is False


def test_failed_filters_wait():
    result = SignalEngine().evaluate(score=90, confirmed=True, filters_ok=False)

    assert result.signal is Signal.AGUARDAR


def test_out_of_range_score_waits():
    result = SignalEngine().evaluate(score=101, confirmed=True)

    assert result.signal is Signal.AGUARDAR
    assert "fora do intervalo" in result.reason


def test_infinite_score_waits():
    result = SignalEngine().evaluate(score=inf, confirmed=True)

    assert result.signal is Signal.AGUARDAR
    assert "inválido" in result.reason


def test_nan_score_waits():
    result = SignalEngine().evaluate(score=nan, confirmed=True)

    assert result.signal is Signal.AGUARDAR
    assert "inválido" in result.reason


def test_boolean_score_is_invalid():
    result = SignalEngine().evaluate(score=True, confirmed=True)

    assert result.signal is Signal.AGUARDAR


def test_non_boolean_confirmation_does_not_execute():
    result = SignalEngine().evaluate(score=90, confirmed=1)

    assert result.signal is Signal.AGUARDAR


def test_non_boolean_filter_does_not_execute():
    result = SignalEngine().evaluate(score=90, confirmed=True, filters_ok=1)

    assert result.signal is Signal.AGUARDAR
