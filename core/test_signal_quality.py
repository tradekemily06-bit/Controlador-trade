import math

from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel, evaluate_signal_quality


def _analysis(signal, score, *, confirmed=True):
    return AnalysisResult(
        signal=signal,
        score=score,
        reason="Teste de qualidade direcional.",
        confirmed=confirmed,
    )


def test_strong_buy_quality_uses_buy_directional_score():
    result = evaluate_signal_quality(_analysis(Signal.COMPRA, 100))

    assert result.actionable is True
    assert result.score == 100
    assert result.level is SignalLevel.FORTE


def test_strong_sell_quality_uses_inverse_directional_score():
    result = evaluate_signal_quality(_analysis(Signal.VENDA, 0))

    assert result.actionable is True
    assert result.score == 100
    assert result.level is SignalLevel.FORTE


def test_buy_and_sell_have_symmetric_quality_bands():
    for buy_score, sell_score, expected_score, expected_level in (
        (70, 30, 70, SignalLevel.MODERADA),
        (80, 20, 80, SignalLevel.FORTE),
        (100, 0, 100, SignalLevel.FORTE),
    ):
        buy = evaluate_signal_quality(_analysis(Signal.COMPRA, buy_score))
        sell = evaluate_signal_quality(_analysis(Signal.VENDA, sell_score))

        assert buy.score == expected_score
        assert buy.level is expected_level
        assert buy.actionable is True
        assert sell.score == expected_score
        assert sell.level is expected_level
        assert sell.actionable is True


def test_direction_and_score_mismatch_is_not_actionable():
    for signal, score in (
        (Signal.COMPRA, 20),
        (Signal.COMPRA, 69),
        (Signal.VENDA, 31),
        (Signal.VENDA, 80),
    ):
        result = evaluate_signal_quality(_analysis(signal, score))
        assert result.actionable is False


def test_unconfirmed_directional_signal_keeps_quality_but_is_not_actionable():
    result = evaluate_signal_quality(
        _analysis(Signal.COMPRA, 100, confirmed=False)
    )

    assert result.actionable is False
    assert result.score == 100
    assert result.level is SignalLevel.FORTE


def test_wait_signal_retains_evidence_quality_but_is_never_actionable():
    result = evaluate_signal_quality(_analysis(Signal.AGUARDAR, 50))

    assert result.actionable is False
    assert result.score == 1
    assert result.level is SignalLevel.FRACA


def test_wait_signal_quality_tracks_distance_from_neutral_score():
    for directional_score, expected_score, expected_level in (
        (15, 70, SignalLevel.MODERADA),
        (10, 80, SignalLevel.FORTE),
        (50, 1, SignalLevel.FRACA),
        (90, 80, SignalLevel.FORTE),
    ):
        result = evaluate_signal_quality(
            _analysis(Signal.AGUARDAR, directional_score, confirmed=False)
        )
        assert result.score == expected_score
        assert result.level is expected_level
        assert result.actionable is False


def test_invalid_scores_fail_closed():
    for score in (math.nan, math.inf, -math.inf, -1, 101, True):
        result = evaluate_signal_quality(_analysis(Signal.COMPRA, score))

        assert result.actionable is False
        assert result.score == 0
        assert result.level is SignalLevel.NENHUMA
