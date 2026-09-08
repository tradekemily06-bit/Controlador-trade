from math import isfinite

from .models import AnalysisResult, Signal


class SignalEngine:
    """Núcleo de decisão independente de corretora."""

    def evaluate(
        self,
        *,
        score: float,
        confirmed: bool,
        filters_ok: bool = True,
        symbol=None,
        timeframe=None,
    ) -> AnalysisResult:
        """Transforma score + filtros + confirmação em uma decisão fail-closed."""

        if not isinstance(score, (int, float)) or isinstance(score, bool) or not isfinite(score):
            return AnalysisResult(
                signal=Signal.AGUARDAR,
                score=score,
                reason="Score inválido; decisão bloqueada por segurança.",
                confirmed=confirmed,
                symbol=symbol,
                timeframe=timeframe,
            )

        if not 0 <= score <= 100:
            return AnalysisResult(
                signal=Signal.AGUARDAR,
                score=score,
                reason="Score fora do intervalo permitido; decisão bloqueada por segurança.",
                confirmed=confirmed,
                symbol=symbol,
                timeframe=timeframe,
            )

        if filters_ok is not True:
            return AnalysisResult(
                signal=Signal.AGUARDAR,
                score=score,
                reason="Filtros de segurança não aprovados.",
                confirmed=confirmed,
                symbol=symbol,
                timeframe=timeframe,
            )

        if confirmed is not True:
            return AnalysisResult(
                signal=Signal.AGUARDAR,
                score=score,
                reason="Aguardando confirmação no fechamento.",
                confirmed=False,
                symbol=symbol,
                timeframe=timeframe,
            )

        if score >= 70:
            return AnalysisResult(
                signal=Signal.COMPRA,
                score=score,
                reason="Score forte e confirmação aprovados para compra.",
                confirmed=True,
                symbol=symbol,
                timeframe=timeframe,
            )

        if score <= 30:
            return AnalysisResult(
                signal=Signal.VENDA,
                score=score,
                reason="Score forte e confirmação aprovados para venda.",
                confirmed=True,
                symbol=symbol,
                timeframe=timeframe,
            )

        return AnalysisResult(
            signal=Signal.AGUARDAR,
            score=score,
            reason="Score insuficiente para entrada.",
            confirmed=True,
            symbol=symbol,
            timeframe=timeframe,
        )
