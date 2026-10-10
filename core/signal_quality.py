from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .models import AnalysisResult, Signal


class SignalLevel(str, Enum):
    FORTE = "FORTE"
    MODERADA = "MODERADA"
    FRACA = "FRACA"
    NENHUMA = "NENHUMA"


@dataclass(frozen=True)
class SignalQuality:
    score: float
    level: SignalLevel
    actionable: bool


class SignalQualityEvaluator:
    """Avalia a força direcional do score; não estima probabilidade de lucro.

    StrategyEngine/SignalEngine usam um score direcional de 0 a 100:
    valores altos favorecem COMPRA e valores baixos favorecem VENDA.
    A qualidade precisa ser calculada na direção do sinal para que compras
    e vendas sejam avaliadas simetricamente. Uma leitura abaixo do mínimo
    de sinal já adotado pelo SignalEngine permanece FRACA e não acionável.
    """

    MIN_ACTIONABLE_SCORE = 70.0
    STRONG_SCORE = 80.0

    def evaluate(self, analysis: AnalysisResult) -> SignalQuality:
        score = analysis.score

        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not isfinite(score)
            or not 0 <= score <= 100
        ):
            return SignalQuality(0.0, SignalLevel.NENHUMA, False)

        if analysis.confirmed is not True:
            return SignalQuality(0.0, SignalLevel.NENHUMA, False)

        # High raw scores favor COMPRA; low raw scores favor VENDA. For an
        # AGUARDAR result, preserve the measured strength of the best
        # directional candidate without promoting it to a trading signal.
        if analysis.signal is Signal.COMPRA:
            directional_score = float(score)
        elif analysis.signal is Signal.VENDA:
            directional_score = 100.0 - float(score)
        else:
            directional_score = float(score) if float(score) >= 50.0 else 100.0 - float(score)

        if directional_score < self.MIN_ACTIONABLE_SCORE:
            return SignalQuality(directional_score, SignalLevel.FRACA, False)

        level = (
            SignalLevel.FORTE
            if directional_score >= self.STRONG_SCORE
            else SignalLevel.MODERADA
        )
        actionable = analysis.signal in (Signal.COMPRA, Signal.VENDA)
        return SignalQuality(directional_score, level, actionable)


def evaluate_signal_quality(analysis: AnalysisResult) -> SignalQuality:
    return SignalQualityEvaluator().evaluate(analysis)
