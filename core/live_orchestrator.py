from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

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
    decision_id: str = ""
    cycle_id: str | None = None
    senior_context: SeniorContextCycle | None = None

    @property
    def executable(self) -> bool:
        return self.decision.decision == FinalDecision.EXECUTAR


class TradingOrchestrator:
    """Liga dados -> análise -> contexto sênior -> qualidade -> decisão."""

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
        decision_id: str | None = None,
        cycle_id: str | None = None,
    ) -> OrchestrationResult:
        timestamp = datetime.now(timezone.utc)
        decision_id = decision_id or str(uuid4())
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id inválido.")
        if cycle_id is not None and (not isinstance(cycle_id, str) or not cycle_id.strip()):
            raise ValueError("cycle_id inválido.")
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
        snapshot = DecisionSnapshot.from_results(
            analysis=analysis,
            quality=quality,
            decision=decision,
            market_context=market_context,
            operational_state=operational_state,
            decision_id=decision_id,
            cycle_id=cycle_id,
        )
        return OrchestrationResult(
            market_data=market_data,
            analysis=analysis,
            quality=quality,
            decision=decision,
            snapshot=snapshot,
            timestamp=timestamp,
            decision_id=decision_id,
            cycle_id=cycle_id,
            senior_context=senior_context,
        )
