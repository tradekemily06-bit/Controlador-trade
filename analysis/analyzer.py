from dataclasses import dataclass

from data.models import Candle

from .pressure import pressure_score
from .rejection import rejection_score
from .structure import structure_score
from .trend import trend_score
from .volume import volume_score


@dataclass(frozen=True)
class TechnicalAnalysis:
    trend: float
    pressure: float
    structure: float
    rejection: float
    volume: float
    confirmation: float


class TechnicalAnalyzer:
    """Analisa candles usando apenas informações de price action."""

    def analyze(
        self,
        candles: list[Candle],
        *,
        confirmed: bool = False,
    ) -> TechnicalAnalysis:
        if not candles:
            raise ValueError("A análise exige pelo menos um candle.")

        return TechnicalAnalysis(
            trend=trend_score(candles),
            pressure=pressure_score(candles[-1]),
            structure=structure_score(candles),
            rejection=rejection_score(candles[-1]),
            volume=volume_score(candles),
            confirmation=100.0 if confirmed else 0.0,
        )
