import math

from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel, evaluate_signal_quality


def _analysis(signal, score, confirmed=True):
    return AnalysisResult(
        signal=signal,
        score=score,
        reason="Teste de qualidade direcional.",
        confirmed=confirmed,
    )


def test_strong_buy_is_strong():
    result = evaluate_signal_quality(_analysis(Signal.COMPRA, 100))

    assert result.actionable is True
    assert result.score == 100
    assert result.level == SignalLevel.FORTE


def test_strong_sell_uses_directional_strength_not_raw_score():
    result = evaluate_signal_quality(_analysis(Signal.VENDA, 0))

    assert result.actionable is True
    assert result.score == 100
    assert result.level == SignalLevel.FORTE


def test_moderate_buy_and_sell_are_symmetric():
    buy = evaluate_signal_quality(_analysis(Signal.COMPRA, 75))
    sell = evaluate_signal_quality(_analysis(Signal.VENDA, 25))

    assert buy.actionable is True
    assert sell.actionable is True
    assert buy.score == sell.score == 75
    assert buy.level is sell.level is SignalLevel.MODERADA


def test_weak_directional_setup_is_not_actionable():
    buy = evaluate_signal_quality(_analysis(Signal.COMPRA, 65))
    sell = evaluate_signal_quality(_analysis(Signal.VENDA, 35))

    for result in (buy, sell):
        assert result.actionable is False
        assert result.score == 65
        assert result.level == SignalLevel.FRACA


def test_unconfirmed_signal_is_not_actionable():
    result = evaluate_signal_quality(_analysis(Signal.COMPRA, 100, confirmed=False))

    assert result.actionable is False
    assert result.score == 0
    assert result.level == SignalLevel.NENHUMA


def test_wait_signal_preserves_weak_candidate_quality_without_becoming_actionable():
    result = evaluate_signal_quality(_analysis(Signal.AGUARDAR, 50))

    assert result.actionable is False
    assert result.score == 50
    assert result.level == SignalLevel.FRACA


def test_wait_with_strong_raw_score_is_not_mislabeled_as_a_strong_opportunity():
    result = evaluate_signal_quality(_analysis(Signal.AGUARDAR, 90))

    assert result.actionable is False
    assert result.score == 0
    assert result.level == SignalLevel.NENHUMA


def test_invalid_scores_fail_closed():
    for score in (math.nan, math.inf, -math.inf, -1, 101, True):
        result = evaluate_signal_quality(_analysis(Signal.COMPRA, score))

        assert result.actionable is False
        assert result.score == 0
        assert result.level == SignalLevel.NENHUMA
