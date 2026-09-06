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
        """Transforma score + filtros + confirmação em uma decisão."""

        if not filters_ok:
            return AnalysisResult(
                signal=Signal.AGUARDAR,
                score=score,
                reason="Filtros de segurança não aprovados.",
                confirmed=confirmed,
                symbol=symbol,
                timeframe=timeframe,
            )

        if not confirmed:
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
