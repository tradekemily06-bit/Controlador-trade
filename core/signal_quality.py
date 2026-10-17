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
    """Classifica a evidência na direção indicada sem conceder autorização de execução."""

    def evaluate(self, analysis: AnalysisResult) -> SignalQuality:
        score = analysis.score

        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not isfinite(score)
            or not 0 <= score <= 100
        ):
            return SignalQuality(
                score=0.0,
                level=SignalLevel.NENHUMA,
                actionable=False,
            )

        if analysis.signal is Signal.COMPRA:
            # O motor direcional define COMPRA a partir de 70.
            quality_score = max(1.0, float(score))
            direction_consistent = score >= 70
        elif analysis.signal is Signal.VENDA:
            # Para VENDA, scores menores representam evidência direcional mais forte.
            quality_score = max(1.0, 100.0 - float(score))
            direction_consistent = score <= 30
        else:
            # AGUARDAR conserva a força da evidência em relação ao ponto neutro.
            # Esta pontuação é informativa e nunca autoriza execução.
            quality_score = max(1.0, abs(float(score) - 50.0) * 2.0)
            direction_consistent = False

        actionable = (
            analysis.confirmed is True
            and analysis.signal in (Signal.COMPRA, Signal.VENDA)
            and direction_consistent
        )

        if quality_score >= 80:
            level = SignalLevel.FORTE
        elif quality_score >= 70:
            level = SignalLevel.MODERADA
        else:
            level = SignalLevel.FRACA

        return SignalQuality(
            score=quality_score,
            level=level,
            actionable=actionable,
        )


def evaluate_signal_quality(analysis: AnalysisResult) -> SignalQuality:
    return SignalQualityEvaluator().evaluate(analysis)
