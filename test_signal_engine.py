from core.models import Signal
from core.signal_engine import SignalEngine


def test_waits_without_confirmation():
    result = SignalEngine().evaluate(score=90, confirmed=False)
    assert result.signal == Signal.AGUARDAR


def test_buy_above_threshold_after_confirmation():
    result = SignalEngine().evaluate(score=80, confirmed=True)
    assert result.signal == Signal.COMPRA


def test_sell_below_threshold_after_confirmation():
    result = SignalEngine().evaluate(score=20, confirmed=True)
    assert result.signal == Signal.VENDA
