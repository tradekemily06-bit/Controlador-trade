import math

from core.models import AnalysisResult, Signal
from core.signal_quality import SignalLevel, evaluate_signal_quality


def test_strong_buy_is_strong():
    result = evaluate_signal_quality(
        AnalysisResult(
            signal=Signal.COMPRA,
            score=100,
            reason="Sinal forte.",
            confirmed=True,
        )
    )

    assert result.actionable is True
    assert result.score == 100
    assert result.level == SignalLevel.FORTE


def test_quality_below_70_is_weak_even_for_directional_sell():
    result = evaluate_signal_quality(
        AnalysisResult(
            signal=Signal.VENDA,
            score=20,
            reason="Sinal de venda.",
            confirmed=True,
        )
    )

    assert result.actionable is True
    assert result.score == 60
    assert result.level == SignalLevel.FRACA


def test_unconfirmed_signal_is_not_actionable():
    result = evaluate_signal_quality(
        AnalysisResult(
            signal=Signal.COMPRA,
            score=100,
            reason="Aguardando fechamento.",
            confirmed=False,
        )
    )

    assert result.actionable is False
    assert result.score == 100
    assert result.level == SignalLevel.FORTE


def test_wait_signal_retains_quality_but_is_not_actionable():
    result = evaluate_signal_quality(
        AnalysisResult(
            signal=Signal.AGUARDAR,
            score=50,
            reason="Score insuficiente.",
            confirmed=True,
        )
    )

    assert result.actionable is False
    assert result.score == 1
    assert result.level == SignalLevel.FRACA


def test_quality_bands_match_ecosystem_contract():
    from core.models import AnalysisResult, Signal
    from core.signal_quality import evaluate_signal_quality

    for directional_score, expected_score, expected_level in (
        (15, 70, SignalLevel.MODERADA),
        (10, 80, SignalLevel.FORTE),
        (50, 1, SignalLevel.FRACA),
    ):
        result = evaluate_signal_quality(
            AnalysisResult(
                signal=Signal.AGUARDAR,
                score=directional_score,
                reason="Teste de qualidade.",
                confirmed=False,
            )
        )
        assert result.score == expected_score
        assert result.level is expected_level
        assert result.actionable is False


def test_invalid_scores_fail_closed():
    for score in (math.nan, math.inf, -math.inf, -1, 101, True):
        result = evaluate_signal_quality(
            AnalysisResult(
                signal=Signal.COMPRA,
                score=score,
                reason="Teste.",
                confirmed=True,
            )
        )

        assert result.actionable is False
        assert result.score == 0
        assert result.level == SignalLevel.NENHUMA
