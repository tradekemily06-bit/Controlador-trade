from dataclasses import dataclass
from enum import Enum

from .market_direction import MarketDirection
from .market_data import Candle
from .liquidity_engine import LiquidityEngine
from .trend_engine import TrendEngine
from .volatility_engine import VolatilityEngine


class MarketContext(str, Enum):
    FAVORAVEL = "FAVORAVEL"
    NEUTRO = "NEUTRO"
    DESFAVORAVEL = "DESFAVORAVEL"


@dataclass(frozen=True)
class MarketContextResult:
    context: MarketContext
    score: float
    reason: str
    direction: MarketDirection


class MarketContextEngine:
    """
    Avalia a qualidade geral do ambiente de mercado.

    A API numérica original é preservada.
    A análise automática por candles é feita por
    evaluate_from_candles().

    Este módulo NÃO gera COMPRA ou VENDA.
    Ele apenas avalia o ambiente de mercado.
    """

    def __init__(
        self,
        *,
        trend_engine=None,
        volatility_engine=None,
        liquidity_engine=None,
    ):
        self.trend_engine = trend_engine or TrendEngine()
        self.volatility_engine = volatility_engine or VolatilityEngine()
        self.liquidity_engine = liquidity_engine or LiquidityEngine()

    def evaluate(
        self,
        *,
        trend_strength: float = 0.0,
        volatility_quality: float = 0.0,
        liquidity_quality: float = 0.0,
        direction: MarketDirection = MarketDirection.NEUTRA,
    ) -> MarketContextResult:

        values = (
            ("trend_strength", trend_strength),
            ("volatility_quality", volatility_quality),
            ("liquidity_quality", liquidity_quality),
        )

        for name, value in values:
            if not 0 <= value <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100.")

        if not isinstance(direction, MarketDirection):
            raise ValueError(
                "direction deve ser uma instância de MarketDirection."
            )

        score = (
            trend_strength * 0.4
            + volatility_quality * 0.3
            + liquidity_quality * 0.3
        )

        if score >= 70:
            return MarketContextResult(
                context=MarketContext.FAVORAVEL,
                score=score,
                reason="Ambiente de mercado favorável.",
                direction=direction,
            )

        if score <= 30:
            return MarketContextResult(
                context=MarketContext.DESFAVORAVEL,
                score=score,
                reason="Ambiente de mercado desfavorável.",
                direction=direction,
            )

        return MarketContextResult(
            context=MarketContext.NEUTRO,
            score=score,
            reason="Ambiente de mercado sem vantagem clara.",
            direction=direction,
        )

    def evaluate_from_candles(
        self,
        *,
        candles: list[Candle],
        liquidity_quality: float | None = None,
    ) -> MarketContextResult:
        """Avalia automaticamente tendência + volatilidade + liquidez."""

        if not candles:
            raise ValueError("É necessário fornecer candles.")

        trend = self.trend_engine.evaluate(candles=candles)
        volatility = self.volatility_engine.evaluate(candles=candles)

        if liquidity_quality is None:
            liquidity = self.liquidity_engine.evaluate(candles=candles)
            liquidity_quality = liquidity.score

        return self.evaluate(
            trend_strength=trend.strength,
            volatility_quality=volatility.score,
            liquidity_quality=liquidity_quality,
            direction=trend.direction,
        )
