from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine, DecisionResult, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operational_state import OperationalState
from core.signal_quality import SignalQuality
from data.feed import MarketDataFeed, MarketDataRequest, MarketDataResult


@dataclass(frozen=True)
class OrchestrationResult:
    """Resultado completo de uma rodada do núcleo, sem executar ordens."""

    market_data: MarketDataResult
    analysis: AnalysisResult
    quality: SignalQuality
    decision: DecisionResult
    snapshot: DecisionSnapshot
    timestamp: datetime

    @property
    def executable(self) -> bool:
        return self.decision.decision == FinalDecision.EXECUTAR


class TradingOrchestrator:
    """Liga dados -> análise -> qualidade -> decisão em uma única fronteira.

    A classe não conhece corretoras e não executa ordens. A execução continua
    sendo responsabilidade explícita do ExecutionGateway.
    """

    def __init__(
        self,
        *,
        feed: MarketDataFeed,
        pipeline: StrategyPipeline,
        decision_engine: DecisionEngine,
        quality_evaluator,
    ) -> None:
        self.feed = feed
        self.pipeline = pipeline
        self.decision_engine = decision_engine
        self.quality_evaluator = quality_evaluator

    def evaluate(
        self,
        request: MarketDataRequest,
        *,
        operational_state: OperationalState | None,
        market_context: MarketContextResult | None,
        confirmed: bool = False,
        filters_ok: bool = True,
        daily_result=None,
        operations_count=None,
        consecutive_losses=None,
    ) -> OrchestrationResult:
        timestamp = datetime.now(timezone.utc)
        market_data = self.feed.fetch(request)
        analysis = self.pipeline.evaluate(
            list(market_data.candles),
            confirmed=confirmed,
            filters_ok=filters_ok,
            symbol=request.symbol,
            timeframe=request.timeframe,
        )
        quality = self.quality_evaluator.evaluate(analysis)
        decision = self.decision_engine.evaluate(
            analysis=analysis,
            market_context=market_context,
            operational_state=operational_state,
            daily_result=daily_result,
            operations_count=operations_count,
            consecutive_losses=consecutive_losses,
        )
        snapshot = DecisionSnapshot.from_results(
            analysis=analysis,
            quality=quality,
            decision=decision,
            market_context=market_context,
            operational_state=operational_state,
        )
        return OrchestrationResult(
            market_data=market_data,
            analysis=analysis,
            quality=quality,
            decision=decision,
            snapshot=snapshot,
            timestamp=timestamp,
        )
