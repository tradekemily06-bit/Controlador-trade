"""Read-only, broker-neutral market analysis for the standalone application."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any, Callable

from security.tenant_context import TenantContext

from analysis.decision_record import DecisionRecord

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.p23_market_data_integrity import MarketDataIntegrity
from core.risk_manager import RiskManager
from core.senior_analysis_gate import SeniorAnalysisGate
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from core.signal_quality import SignalQualityEvaluator
from core.live_orchestrator import TradingOrchestrator
from core.unified_intelligence import UnifiedIntelligence
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.feed import MarketDataFeed, MarketDataProvider, MarketDataRequest
from data.models import Candle
from data.timeframes import get_timeframe_interval, normalize_timeframe


class StandaloneMarketAnalysisService:
    """Uses the existing analysis pipeline but never creates an execution path."""

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        source: str,
        intelligence: UnifiedIntelligence,
        decision_sink: Callable[..., bool | None] | None = None,
    ) -> None:
        if provider is None:
            raise ValueError("market data provider is required")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("market data source is required")
        self.provider = provider
        self.source = source.strip()
        self.intelligence = intelligence
        if decision_sink is not None and not callable(decision_sink):
            raise ValueError("decision_sink must be callable")
        self.decision_sink = decision_sink
        self.feed = MarketDataFeed(provider, source=self.source)
        self.orchestrator = TradingOrchestrator(
            feed=self.feed,
            pipeline=StrategyPipeline(),
            decision_engine=DecisionEngine(RiskManager()),
            quality_evaluator=SignalQualityEvaluator(),
            senior_context_builder=self._build_senior_context,
        )

    def _decision_record_id(self, symbol: str, timeframe: str, candle_at: str) -> str:
        # Source/account identity belongs in the deduplication key: two
        # different broker accounts can legitimately analyze the same candle.
        identity = f"{self.source}|{symbol}|{timeframe}|{candle_at}"
        return "market-" + sha256(identity.encode("utf-8")).hexdigest()[:32]

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
        decision_context: TenantContext | None = None,
        live_candle: Candle | None = None,
    ) -> dict[str, Any]:
        if not isinstance(confirmed, bool) or not isinstance(filters_ok, bool):
            raise ValueError("confirmed and filters_ok must be booleans")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol is required")
        timeframe = normalize_timeframe(timeframe)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 3 <= limit <= 1000:
            raise ValueError("limit must be an integer from 3 to 1000")
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        result = self.orchestrator.evaluate(
            request,
            operational_state=None,
            market_context=None,
            confirmed=confirmed,
            filters_ok=filters_ok,
            filters_required=True,
            live_candle=live_candle,
        )
        interval = int(get_timeframe_interval(timeframe).total_seconds())
        # Keep the tolerance proportional to the selected timeframe.
        # A five-minute floor made 1m feeds appear current for several missed bars.
        max_age = max(30, interval * 2)
        integrity = MarketDataRuntimeIntegrity(
            integrity=MarketDataIntegrity(max_age_seconds=max_age)
        ).assess(
            BrokerMarketDataSnapshot(
                symbol=symbol,
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
        senior_posture = (
            senior.senior_assessment.posture.value
            if senior is not None else "INSUFFICIENT"
        )
        gated = (
            SeniorAnalysisGate().evaluate(
                analysis=result.analysis,
                senior_context=senior,
            )
            if senior is not None else None
        )
        senior_reassessment = senior_posture in {"REASSESS", "INSUFFICIENT"}
        safe = (
            integrity.safe_for_analysis
            and senior_complete
            and not senior_reassessment
            and gated is not None
            and gated.signal.value != "AGUARDAR"
        )
        signal = gated.signal.value if safe else "AGUARDAR"
        reason = gated.reason if gated is not None else result.analysis.reason
        if not integrity.safe_for_analysis:
            reason = f"Análise suspensa: {integrity.message}."
        elif not senior_complete or senior_reassessment:
            reason = "Análise suspensa: o raciocínio sênior identificou contexto incompleto ou uma condição que exige reavaliação."
        elif gated is not None and gated.signal.value == "AGUARDAR":
            reason = gated.reason

        score = result.quality.score
        score_semantics = "força da evidência, não probabilidade de acerto"
        signal_visual = {
            "color": {
                "COMPRA": "GREEN",
                "VENDA": "RED",
                "AGUARDAR": "YELLOW",
            }[signal],
            "arrow": {
                "COMPRA": "UP",
                "VENDA": "DOWN",
                "AGUARDAR": "NONE",
            }[signal],
            "score_color": {
                "COMPRA": "GREEN",
                "VENDA": "RED",
                "AGUARDAR": "YELLOW",
            }[signal],
            "profit_probability_color": {
                "COMPRA": "GREEN",
                "VENDA": "RED",
                "AGUARDAR": "YELLOW",
            }[signal],
        }
        signal_card = {
            "symbol": symbol,
            "direction": signal,
            "timeframe": timeframe,
            "visual": signal_visual,
            "score": score,
            "score_type": "EVIDENCE_STRENGTH",
            "score_semantics": score_semantics,
            "display": f"{symbol} · {signal} · {score}/100",
            "state": "READY_FOR_MANUAL_REVIEW" if safe else "WAIT",
            "probability_of_profit": None,
            "profit_probability": {
                "status": "NOT_CALIBRATED",
                "value": None,
                "unit": "PERCENT",
                "account_mode": None,
                "sample_count": 0,
                "calibration_required": True,
                "reason": "Estimativa indisponível até haver resultados representativos e validados para este contexto DEMO ou REAL.",
            },
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "manual_entry_only": True,
            "execution_authorized": False,
            "order_submitted": False,
        }
        response = {
            "status": "ANALYZED" if safe else "REASSESS_REQUIRED",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal,
            "candidate_signal": candidate_signal,
            "score": score,
            "score_semantics": score_semantics,
            "signal_card": signal_card,
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
                    "posture": senior_posture,
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
        response["decision_memory"] = {"status": "NOT_CONFIGURED"}
        if self.decision_sink is not None:
            candle_at = result.market_data.candles[-1].timestamp.isoformat()
            stable_id = self._decision_record_id(symbol, timeframe, candle_at)
            decision_record = DecisionRecord(
                decision_id=stable_id,
                created_at=candle_at,
                symbol=symbol,
                timeframe=timeframe,
                signal=signal,
                score=float(score),
                confirmed=bool(result.analysis.confirmed),
                reason=reason,
                execution_allowed=False,
            )
            try:
                stored = (
                    self.decision_sink(decision_record)
                    if decision_context is None
                    else self.decision_sink(decision_record, decision_context)
                )
                response["decision_memory"] = {
                    "status": "SAVED" if stored is not False else "ALREADY_RECORDED",
                    "decision_id": stable_id,
                    "scope": "TENANT_AND_SUBJECT",
                }
            except Exception as exc:
                response["decision_memory"] = {
                    "status": "PERSISTENCE_ERROR",
                    "error_class": type(exc).__name__,
                    "decision_id": stable_id,
                }
        return response
