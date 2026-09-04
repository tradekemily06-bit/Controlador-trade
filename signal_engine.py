from .models import AnalysisResult, Signal


class SignalEngine:
    """Núcleo de decisão. Não conhece corretora, plataforma ou API."""

    def evaluate(self, *, score: float, confirmed: bool, symbol=None, timeframe=None):
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
            signal = Signal.COMPRA
            reason = "Condições mínimas de compra atingidas."
        elif score <= 30:
            signal = Signal.VENDA
            reason = "Condições mínimas de venda atingidas."
        else:
            signal = Signal.AGUARDAR
            reason = "Score insuficiente para entrada."

        return AnalysisResult(
            signal=signal,
            score=score,
            reason=reason,
            confirmed=confirmed,
            symbol=symbol,
            timeframe=timeframe,
        )
