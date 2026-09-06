from dataclasses import dataclass

from .market_data import Candle


@dataclass(frozen=True)
class LiquidityResult:
    score: float
    average_volume: float
    latest_volume: float
    volume_ratio: float
    reason: str


class LiquidityEngine:
    """Avalia a atividade de mercado usando o volume dos candles."""

    def evaluate(self, *, candles: list[Candle]) -> LiquidityResult:
        if len(candles) < 2:
            raise ValueError("São necessários pelo menos 2 candles.")

        volumes = [candle.volume for candle in candles]
        average_volume = sum(volumes) / len(volumes)
        latest_volume = volumes[-1]

        if average_volume <= 0:
            return LiquidityResult(
                score=0.0,
                average_volume=average_volume,
                latest_volume=latest_volume,
                volume_ratio=0.0,
                reason="Sem volume suficiente para avaliar a liquidez.",
            )

        volume_ratio = latest_volume / average_volume

        if volume_ratio >= 1.5:
            score = 100.0
            reason = "Atividade de volume muito alta."

        elif volume_ratio >= 1.0:
            score = 75.0
            reason = "Atividade de volume adequada."

        elif volume_ratio >= 0.5:
            score = 40.0
            reason = "Atividade de volume moderada."

        else:
            score = 10.0
            reason = "Atividade de volume muito baixa."

        return LiquidityResult(
            score=score,
            average_volume=average_volume,
            latest_volume=latest_volume,
            volume_ratio=volume_ratio,
            reason=reason,
        )
