from __future__ import annotations

from data.models import Candle

from core.models import AnalysisResult
from core.strategy_engine import StrategyEngine, StrategyInput

from .analyzer import TechnicalAnalyzer


class StrategyPipeline:
    """Liga candles, análise técnica, score e sinal sem conhecer corretora."""

    def __init__(
        self,
        *,
        analyzer: TechnicalAnalyzer | None = None,
        strategy_engine: StrategyEngine | None = None,
    ) -> None:
        self.analyzer = analyzer or TechnicalAnalyzer()
        self.strategy_engine = strategy_engine or StrategyEngine()

    def evaluate(
        self,
        candles: list[Candle],
        *,
        confirmed: bool = False,
        filters_ok: bool = True,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> AnalysisResult:
        analysis = self.analyzer.analyze(candles, confirmed=confirmed)

        return self.strategy_engine.evaluate(
            StrategyInput(
                trend=analysis.trend,
                pressure=analysis.pressure,
                structure=analysis.structure,
                rejection=analysis.rejection,
                volume=analysis.volume,
                confirmation=analysis.confirmation,
                confirmed=confirmed,
                filters_ok=filters_ok,
                symbol=symbol,
                timeframe=timeframe,
            )
        )
