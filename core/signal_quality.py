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
    """Classifica a qualidade do sinal sem alterar a decisão do motor."""

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

        actionable = (
            analysis.confirmed is True
            and analysis.signal in (Signal.COMPRA, Signal.VENDA)
        )

        if not actionable:
            return SignalQuality(
                score=0.0,
                level=SignalLevel.NENHUMA,
                actionable=False,
            )

        quality_score = abs(score - 50.0) * 2.0

        if quality_score >= 80:
            level = SignalLevel.FORTE
        elif quality_score >= 60:
            level = SignalLevel.MODERADA
        else:
            level = SignalLevel.FRACA

        return SignalQuality(
            score=quality_score,
            level=level,
            actionable=True,
        )


def evaluate_signal_quality(analysis: AnalysisResult) -> SignalQuality:
    return SignalQualityEvaluator().evaluate(analysis)
