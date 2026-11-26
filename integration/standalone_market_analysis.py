"""Read-only, broker-neutral market analysis for the standalone application."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.p23_market_data_integrity import MarketDataIntegrity
from core.risk_manager import RiskManager
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from core.signal_quality import SignalQualityEvaluator
from core.trading_runtime import TradingRuntime
from core.live_orchestrator import TradingOrchestrator
from core.unified_intelligence import UnifiedIntelligence
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.feed import MarketDataFeed, MarketDataProvider, MarketDataRequest


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class StandaloneMarketAnalysisService:
    """Uses the existing analysis pipeline but never creates an execution path."""

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        source: str,
        intelligence: UnifiedIntelligence,
    ) -> None:
        if provider is None:
            raise ValueError("market data provider is required")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("market data source is required")
        self.provider = provider
        self.source = source.strip()
        self.intelligence = intelligence
        self.feed = MarketDataFeed(provider, source=self.source)
        self.orchestrator = TradingOrchestrator(
            feed=self.feed,
            pipeline=StrategyPipeline(),
            decision_engine=DecisionEngine(RiskManager()),
            quality_evaluator=SignalQualityEvaluator(),
            senior_context_builder=self._build_senior_context,
        )

    def _build_senior_context(self, candles, operational_state):
        if len(candles) < 3:
            return None
        request = SeniorContextInput(
            context_id=f"standalone:{candles[-1].timestamp.isoformat()}",
            candles=tuple(candles),
            available_nodes=("market_data", "price_history", "temporal_context"),
            observed_nodes=("market_data", "price_history", "temporal_context"),
            gaps={},
            relationships_reviewed=(
                "market_data-price_history",
                "price_history-temporal_context",
            ),
            risk_observations=(
                RiskObservation(
                    RiskDomain.DATA_QUALITY,
                    f"{len(candles)} candles normalizados e recebidos pelo provider {self.source}.",
                    True,
                    ("market_data_feed", "candle_validator"),
                ),
            ),
            available_risk_domains=(RiskDomain.DATA_QUALITY,),
        )
        return self.intelligence.assess_market(request)

    def analyze(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int = 120,
        confirmed: bool = False,
        filters_ok: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(confirmed, bool) or not isinstance(filters_ok, bool):
            raise ValueError("confirmed and filters_ok must be booleans")
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        result = self.orchestrator.evaluate(
            request,
            operational_state=None,
            market_context=None,
            confirmed=confirmed,
            filters_ok=filters_ok,
            filters_required=True,
        )
        interval = _TIMEFRAME_SECONDS.get(timeframe.strip().lower())
        max_age = max(300, interval * 2) if interval is not None else 300
        integrity = MarketDataRuntimeIntegrity(
            integrity=MarketDataIntegrity(max_age_seconds=max_age)
        ).assess(
            BrokerMarketDataSnapshot(
                symbol=result.market_data.candles[-1] and symbol,
                timeframe=timeframe,
                candles=result.market_data.candles,
                source=result.market_data.source,
                received_at=result.market_data.received_at,
            ),
            now=datetime.now().astimezone(),
            expected_interval_seconds=interval,
        )

        candidate_signal = result.analysis.signal.value
        senior = result.senior_context
        senior_complete = senior is not None and senior.quality.value == "COMPLETE"
        safe = integrity.safe_for_analysis and senior_complete
        signal = candidate_signal if safe else "AGUARDAR"
        reason = result.analysis.reason
        if not integrity.safe_for_analysis:
            reason = f"Análise suspensa: {integrity.message}."
        elif not senior_complete:
            reason = "Análise suspensa: o contexto sênior está incompleto ou exige reavaliação."

        return {
            "status": "ANALYZED" if safe else "REASSESS_REQUIRED",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal,
            "candidate_signal": candidate_signal,
            "score": result.quality.score,
            "score_semantics": "força da evidência, não probabilidade de acerto",
            "reason": reason,
            "confirmed": result.analysis.confirmed,
            "quality": {
                "score": result.quality.score,
                "level": result.quality.level.value,
                "actionable": False,
            },
            "market_data": {
                "source": result.market_data.source,
                "received_at": result.market_data.received_at.isoformat(),
                "last_candle_at": result.market_data.candles[-1].timestamp.isoformat(),
                "candle_count": len(result.market_data.candles),
                "ohlcv": [
                    {
                        "timestamp": candle.timestamp.isoformat(),
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
                    for candle in result.market_data.candles[-120:]
                ],
            },
            "data_integrity": integrity.to_dict(),
            "senior_context": (
                {
                    "cycle_id": senior.cycle_id,
                    "quality": senior.quality.value,
                    "posture": senior.senior_assessment.posture.value,
                    "unresolved_questions": list(senior.unresolved_questions),
                    "execution_authorized": False,
                }
                if senior is not None else {"status": "INSUFFICIENT"}
            ),
            "decision": "ANALYSIS_ONLY",
            "execution_allowed": False,
            "execution_authorized": False,
            "order_submitted": False,
        }
