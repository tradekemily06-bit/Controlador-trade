from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine, DecisionResult, FinalDecision
from core.decision_snapshot import DecisionSnapshot
from core.market_context import MarketContextEngine, MarketContextResult
from core.models import AnalysisResult
from core.operational_state import OperationalState
from core.signal_quality import SignalQuality
from core.indicator_evidence import IndicatorEvidence, calculate_indicator_evidence
from core.indicator_sources import (
    ExternalIndicatorReading,
    IndicatorReadingProvider,
    is_fresh_indicator_reading,
)
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
    indicator_evidence: IndicatorEvidence | None = None
    external_indicator_reading: ExternalIndicatorReading | None = None
    external_indicator_status: str = "NOT_CONFIGURED"
    indicators_enabled: bool = True

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
        market_context_engine: MarketContextEngine | None = None,
        senior_context_builder: Callable[[list, OperationalState | None], SeniorContextCycle | None] | None = None,
        indicator_provider: IndicatorReadingProvider | None = None,
    ) -> None:
        self.feed = feed
        self.pipeline = pipeline
        self.decision_engine = decision_engine
        self.quality_evaluator = quality_evaluator
        self.market_context_engine = market_context_engine or MarketContextEngine()
        self.senior_context_builder = senior_context_builder
        self.indicator_provider = indicator_provider

    def evaluate(
        self,
        request: MarketDataRequest,
        *,
        operational_state: OperationalState | None,
        market_context: MarketContextResult | None,
        senior_context: SeniorContextCycle | None = None,
        confirmed: bool = False,
        filters_ok: bool = True,
        indicators_enabled: bool = True,
        daily_result=None,
        operations_count=None,
        consecutive_losses=None,
    ) -> OrchestrationResult:
        timestamp = datetime.now(timezone.utc)
        market_data = self.feed.fetch(request)
        # Indicator evidence is derived from the same validated candle snapshot;
        # it is intentionally informational and does not authorize or alter a decision.
        indicator_evidence = (
            calculate_indicator_evidence(
                market_data.candles,
                source=f"{market_data.source}:CONTROLADOR_CALCULADO",
            )
            if indicators_enabled and len(market_data.candles) >= 35
            else None
        )
        external_indicator_reading = None
        external_indicator_status = "NOT_CONFIGURED" if indicators_enabled else "DISABLED_BY_PREFERENCE"
        if indicators_enabled and self.indicator_provider is not None:
            try:
                candidate = self.indicator_provider.read(
                    symbol=request.symbol, timeframe=request.timeframe, now=timestamp
                )
                if candidate is None:
                    external_indicator_status = "UNAVAILABLE"
                elif candidate.symbol.upper() != request.symbol.upper() or candidate.timeframe.upper() != request.timeframe.upper():
                    external_indicator_status = "REJECTED_SYMBOL_OR_TIMEFRAME_MISMATCH"
                elif not is_fresh_indicator_reading(candidate, now=timestamp, max_age_seconds=300):
                    external_indicator_status = "REJECTED_STALE_READING"
                else:
                    external_indicator_reading = candidate
                    external_indicator_status = "AVAILABLE_EVIDENCE_ONLY"
            except Exception:
                # A provider outage or malformed external payload must not stop
                # the core analysis or grant any additional execution authority.
                external_indicator_status = "UNAVAILABLE_PROVIDER_ERROR"
        if market_context is None:
            market_context = self.market_context_engine.evaluate_from_candles(
                candles=list(market_data.candles),
            )
        analysis = self.pipeline.evaluate(
            list(market_data.candles),
            confirmed=confirmed,
            filters_ok=filters_ok,
            symbol=request.symbol,
            timeframe=request.timeframe,
        )
        quality = self.quality_evaluator.evaluate(analysis)
        if senior_context is None and self.senior_context_builder is not None:
            senior_context = self.senior_context_builder(list(market_data.candles), operational_state)
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
        )
        return OrchestrationResult(
            market_data=market_data,
            analysis=analysis,
            quality=quality,
            decision=decision,
            snapshot=snapshot,
            timestamp=timestamp,
            senior_context=senior_context,
            indicator_evidence=indicator_evidence,
            external_indicator_reading=external_indicator_reading,
            external_indicator_status=external_indicator_status,
            indicators_enabled=bool(indicators_enabled),
        )
