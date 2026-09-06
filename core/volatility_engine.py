from dataclasses import dataclass

from .market_data import Candle


@dataclass(frozen=True)
class VolatilityResult:
    score: float
    average_range_percent: float
    reason: str


class VolatilityEngine:
    """Avalia a qualidade da volatilidade a partir dos candles."""

    def evaluate(self, *, candles: list[Candle]) -> VolatilityResult:
        if len(candles) < 2:
            raise ValueError("São necessários pelo menos 2 candles.")

        ranges = []

        for candle in candles:
            range_percent = ((candle.high - candle.low) / candle.close) * 100
            ranges.append(range_percent)

        average_range_percent = sum(ranges) / len(ranges)

        # Faixa inicial conservadora.
        # O score representa adequação da volatilidade para execução,
        # não uma previsão de direção.
        if average_range_percent >= 1.0:
            score = 100.0
            reason = "Volatilidade alta para execução."

        elif average_range_percent >= 0.5:
            score = 70.0
            reason = "Volatilidade adequada para execução."

        elif average_range_percent >= 0.2:
            score = 40.0
            reason = "Volatilidade moderada."

        else:
            score = 10.0
            reason = "Volatilidade muito baixa para execução."

        return VolatilityResult(
            score=score,
            average_range_percent=average_range_percent,
            reason=reason,
        )
