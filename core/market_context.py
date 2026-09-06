from dataclasses import dataclass
from enum import Enum


class MarketContext(str, Enum):
    FAVORAVEL = "FAVORAVEL"
    NEUTRO = "NEUTRO"
    DESFAVORAVEL = "DESFAVORAVEL"


class MarketDirection(str, Enum):
    ALTA = "ALTA"
    BAIXA = "BAIXA"
    NEUTRA = "NEUTRA"


@dataclass(frozen=True)
class MarketContextResult:
    context: MarketContext
    score: float
    reason: str
    direction: MarketDirection


class MarketContextEngine:
    """
    Avalia a qualidade geral do ambiente de mercado.

    Os parâmetros são notas de qualidade de 0 a 100:
    - trend_strength: força da tendência.
    - volatility_quality: qualidade da volatilidade para execução.
    - liquidity_quality: qualidade da liquidez para execução.

    Este módulo NÃO gera COMPRA ou VENDA.
    Ele apenas avalia o ambiente de mercado.
    """

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
