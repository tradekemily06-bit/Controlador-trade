from dataclasses import dataclass

from .market_data import Candle
from .market_direction import MarketDirection


@dataclass(frozen=True)
class TrendResult:
    direction: MarketDirection
    strength: float
    reason: str


class TrendEngine:
    """Calcula tendência a partir da estrutura dos candles."""

    def evaluate(self, *, candles: list[Candle]) -> TrendResult:
        if len(candles) < 3:
            raise ValueError("São necessários pelo menos 3 candles.")

        previous = candles[-3]
        current = candles[-1]

        middle = candles[-2]

        higher_high = current.high > middle.high > previous.high
        higher_low = current.low > middle.low > previous.low

        lower_high = current.high < middle.high < previous.high
        lower_low = current.low < middle.low < previous.low

        if higher_high and higher_low:
            return TrendResult(
                direction=MarketDirection.ALTA,
                strength=100.0,
                reason="Estrutura de alta com topos e fundos ascendentes.",
            )

        if lower_high and lower_low:
            return TrendResult(
                direction=MarketDirection.BAIXA,
                strength=100.0,
                reason="Estrutura de baixa com topos e fundos descendentes.",
            )

        if current.close > previous.close:
            return TrendResult(
                direction=MarketDirection.ALTA,
                strength=50.0,
                reason="Movimento recente de alta sem estrutura completa.",
            )

        if current.close < previous.close:
            return TrendResult(
                direction=MarketDirection.BAIXA,
                strength=50.0,
                reason="Movimento recente de baixa sem estrutura completa.",
            )

        return TrendResult(
            direction=MarketDirection.NEUTRA,
            strength=0.0,
            reason="Sem direção clara na estrutura recente.",
        )
