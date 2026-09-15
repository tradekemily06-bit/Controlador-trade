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
from core.senior_context_cycle import SeniorContextCycle
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
    senior_context: SeniorContextCycle | None = None

    @property
    def executable(self) -> bool:
        return self.decision.decision == FinalDecision.EXECUTAR


class TradingOrchestrator:
    """Liga dados -> análise -> contexto sênior -> qualidade -> decisão.

    A classe não conhece corretoras e não executa ordens. A execução continua
    sendo responsabilidade explícita do ExecutionGateway, após a admissão sênior.
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
        senior_context: SeniorContextCycle | None = None,
        confirmed: bool = False,
        filters_ok: bool = True,
        daily_result=None,
        operations_count=None,
        consecutive_losses=None,
    ) -> OrchestrationResult:
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
            senior_context=senior_context,
            daily_result=daily_result,
            operations_count=operations_count,
            consecutive_losses=consecutive_losses,
        )
        # This timestamp represents the completed decision, not the beginning
        # of the data-fetch/analysis cycle. It is the freshness anchor carried
        # by both the orchestration result and its immutable decision snapshot.
        timestamp = datetime.now(timezone.utc)
        snapshot = DecisionSnapshot.from_results(
            analysis=analysis,
            quality=quality,
            decision=decision,
            market_context=market_context,
            operational_state=operational_state,
            created_at=timestamp,
        )
        return OrchestrationResult(
            market_data=market_data,
            analysis=analysis,
            quality=quality,
            decision=decision,
            snapshot=snapshot,
            timestamp=timestamp,
            senior_context=senior_context,
        )
