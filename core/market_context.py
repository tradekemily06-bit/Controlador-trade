from dataclasses import dataclass
from enum import Enum


class MarketContext(str, Enum):
    FAVORAVEL = "FAVORAVEL"
    NEUTRO = "NEUTRO"
    DESFAVORAVEL = "DESFAVORAVEL"


@dataclass(frozen=True)
class MarketContextResult:
    context: MarketContext
    score: float
    reason: str


class MarketContextEngine:
    """Avalia o contexto geral do mercado antes da execução."""

    def evaluate(
        self,
        *,
        trend: float = 0.0,
        volatility: float = 0.0,
        liquidity: float = 0.0,
    ) -> MarketContextResult:
        for name, value in (
            ("trend", trend),
            ("volatility", volatility),
            ("liquidity", liquidity),
        ):
            if not 0 <= value <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100.")

        score = (
            trend * 0.4
            + volatility * 0.3
            + liquidity * 0.3
        )

        if score >= 70:
            return MarketContextResult(
                context=MarketContext.FAVORAVEL,
                score=score,
                reason="Contexto de mercado favorável.",
            )

        if score <= 30:
            return MarketContextResult(
                context=MarketContext.DESFAVORAVEL,
                score=score,
                reason="Contexto de mercado desfavorável.",
            )

        return MarketContextResult(
            context=MarketContext.NEUTRO,
            score=score,
            reason="Contexto de mercado sem vantagem clara.",
        )
