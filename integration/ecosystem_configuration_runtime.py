from __future__ import annotations

from dataclasses import asdict
from typing import Any
from pathlib import Path
import tempfile

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from core.operational_alerts import OperationalIncident, build_operational_incidents
from security_audit import AUDIT
from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine
from core.live_orchestrator import TradingOrchestrator
from core.signal_quality import SignalQualityEvaluator
from core.trading_runtime import TradingRuntime
from data.feed import MarketDataFeed, MarketDataRequest
from core.execution_coordinator import ExecutionCoordinator, ExecutionPlan
from core.demo_readiness import DemoReadiness, DemoReadinessReport
from core.unified_safety_gate import UnifiedSafetyGate
from core.runtime_config import RuntimeConfig
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.p23_market_data_integrity import MarketDataIntegrity
from core.p39_pretrade_risk import PreTradeRiskEvaluator, RiskAssessment, RiskDecision, RiskProposal
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment, RiskBudgetEvaluator, RiskBudgetLimits, RiskBudgetState
from core.automation_risk_policy import AutomationRiskPolicy
from core.p41_controlled_automation import AutomationPolicy
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
from execution.mt5_session_lock import serialized_mt5_session
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from core.ecosystem_state_store import EcosystemStateStore
from core.models import AnalysisResult, Signal
from core.p122_broker_market_data import BrokerMarketDataRequest, BrokerMarketDataSnapshot
from core.candle_analysis_evaluator import evaluate_candle_snapshot
from core.historical_trade_simulator import HistoricalBacktestConfig, HistoricalSignal, HistoricalTradeSimulator
from core.senior_analysis_gate import SeniorAnalysisGate
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from integration.ecosystem_service import EcosystemService
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary
from integration.p137_operational_risk_bridge import OperationalRiskBridge
from execution.mt5_instrument_universe import discover_mt5_instruments
from integration.mt5_asset_suitability_bridge import prioritize_mt5_assets


class ConfiguredEcosystemService(EcosystemService):
    """Ecosystem service with preferences, notifications and senior analysis wired in."""

    def __init__(self, *args: Any, execution_provider: str = "paper", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        normalized_provider = execution_provider.strip().lower() if isinstance(execution_provider, str) else ""
        self.execution_provider = normalized_provider or "paper"
        if self.operational_runtime is not None:
            state_path = self.operational_runtime.checkpoint_store.path.parent / "ecosystem-state.sqlite"
        else:
            # Isolated fallback for unit/test instances; the shared durable store
            # belongs to the real operational runtime and is only used there.
            state_path = Path(tempfile.mkdtemp(prefix="controlador-ecosystem-state-")) / "ecosystem-state.sqlite"
        self.state_store = EcosystemStateStore(state_path)
        self.restore_learning_state()
        persisted_preferences = self.state_store.load_preferences()
        self.preferences = EcosystemPreferencesStore.from_dict(persisted_preferences) if persisted_preferences else EcosystemPreferencesStore()
        self.notifications = EcosystemNotificationCenter()
        self.notifications.restore(self.state_store.load_notifications())
        self.state_store.save_preferences(self.preferences.preferences)
        self.senior_analysis_gate = SeniorAnalysisGate()
        self.operational_risk_bridge = OperationalRiskBridge(self.risk)
        self.automation_risk_policy = AutomationRiskPolicy.from_environment()
        self.mt5_market_adapter = ICMarketsMT5DemoMarketDataAdapter()
        self.mt5_operational_adapter = ICMarketsMT5DemoAdapter()
        if self.operational_runtime is not None:
            self.trading_runtime = TradingRuntime(
                orchestrator=TradingOrchestrator(
                    feed=MarketDataFeed(self.mt5_market_adapter, source="IC Markets MT5 DEMO"),
                    pipeline=StrategyPipeline(),
                    decision_engine=DecisionEngine(self.risk),
                    quality_evaluator=SignalQualityEvaluator(),
                    senior_context_builder=self._build_mt5_senior_context,
                ),
                coordinator=ExecutionCoordinator(self.operational_runtime.gateway),
                market_data_state=self.operational_runtime.market_data,
                automation_service=self.automation,
            )
        else:
            self.trading_runtime = None

    def analyze(self, payload: dict[str, Any]):
        """Require senior context and operational risk for actionable analysis."""
        try:
            context_input = SeniorAnalysisBoundary.build_input(payload)
        except ValueError as exc:
            safe = AnalysisResult(
                signal=Signal.AGUARDAR,
                score=float(payload.get("score", 0)),
                reason=f"Análise sênior não pode ser concluída: {exc}.",
                confirmed=False,
                symbol=payload.get("symbol"),
                timeframe=payload.get("timeframe"),
            )
            return self._record_analysis(safe)

        senior_context = self.senior_context.assess(context_input)
        candidate = self.engine.evaluate(
            score=payload.get("score", 50),
            confirmed=payload.get("confirmed", False),
            filters_ok=payload.get("filters_ok", True),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
        )
        operational_risk = self.operational_risk_bridge.evaluate(payload)
        gated = self.senior_analysis_gate.evaluate(
            analysis=candidate,
            senior_context=senior_context,
            operational_risk=operational_risk,
        )
        return self._record_analysis(gated)

    def _record_analysis(self, result):
        from analysis.decision_record import DecisionRecord
        record = DecisionRecord.from_analysis(result)
        self.memory.append(record)
        self.store.save(record)
        return record

    def _build_mt5_senior_context(self, candles, operational_state):
        """Build senior context from the exact candles already fetched for this cycle."""
        observations = []
        available_domains = []
        if operational_state is not None:
            if operational_state.balance is not None and operational_state.equity is not None:
                available_domains.append(RiskDomain.CAPITAL)
                observations.append(RiskObservation(
                    RiskDomain.CAPITAL,
                    f"Capital observado no snapshot DEMO: balance={operational_state.balance}, equity={operational_state.equity}.",
                    True,
                    ("mt5.account_info",),
                ))
            if (
                operational_state.open_positions is not None
                and operational_state.net_position is not None
                and operational_state.exposure is not None
            ):
                available_domains.append(RiskDomain.POSITION)
                observations.append(RiskObservation(
                    RiskDomain.POSITION,
                    f"Posição observada no snapshot DEMO: abertas={operational_state.open_positions}, net={operational_state.net_position}, exposição={operational_state.exposure}.",
                    True,
                    ("mt5.positions_get",),
                ))
        if candles:
            available_domains.append(RiskDomain.DATA_QUALITY)
            observations.append(RiskObservation(
                RiskDomain.DATA_QUALITY,
                f"Dados de mercado normalizados e observados no ciclo: {len(candles)} candles concluídos.",
                True,
                ("mt5.copy_rates_from_pos:start_pos=1",),
            ))
        context_id = f"mt5:{candles[-1].timestamp.isoformat()}" if candles else "mt5:empty"
        nodes = ("market_data", "price_history", "operational_state") if operational_state is not None else ("market_data", "price_history")
        relationships = ("market_data-price_history", "price_history-temporal_context")
        if operational_state is not None:
            relationships += ("market_data-operational_state",)
        return self.senior_context.assess(SeniorContextInput(
            context_id=context_id,
            candles=tuple(candles),
            available_nodes=nodes,
            observed_nodes=nodes,
            gaps={},
            relationships_reviewed=relationships,
            risk_observations=tuple(observations),
            available_risk_domains=tuple(available_domains),
        ))

    def _build_mt5_automation_readiness(self, intent, orchestration) -> DemoReadinessReport:
        """Evaluate the existing DEMO safety stack from this exact market cycle."""
        if self.operational_runtime is None:
            return DemoReadinessReport(False, ("runtime operacional não conectado.",))
        integrity = MarketDataIntegrity().assess(
            tuple(orchestration.market_data.candles),
            now=orchestration.timestamp,
            expected_interval_seconds={
                "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                "1h": 3600, "4h": 14400, "1d": 86400,
            }.get(orchestration.market_data.timeframe.lower()),
        )
        recovery = self.operational_runtime.recovery.assess()
        config = RuntimeConfig(
            symbol=orchestration.market_data.symbol,
            timeframe=orchestration.market_data.timeframe,
            amount=intent.amount,
            duration_seconds=intent.duration_seconds,
        )
        return DemoReadiness(
            UnifiedSafetyGate(kill_switch=self.operational_runtime.kill_switch)
        ).evaluate(
            config=config,
            market_data=integrity,
            recovery=recovery,
            intent=intent,
        )

    def _build_mt5_pretrade_risk(self, operational_state, intent, orchestration) -> RiskAssessment:
        """Evaluate P39 in MT5 volume units; missing policy/state blocks."""
        limits = self.automation_risk_policy.limits()
        gross_volume = getattr(operational_state, "gross_position_volume", None)
        if limits is None:
            return RiskAssessment(RiskDecision.BLOCKED, 0.0, "limites P39 de volume não configurados.")
        if gross_volume is None:
            return RiskAssessment(RiskDecision.BLOCKED, 0.0, "volume bruto das posições DEMO indisponível.")
        return PreTradeRiskEvaluator().evaluate(
            RiskProposal(
                order_amount=float(intent.amount),
                current_exposure=float(gross_volume),
            ),
            limits,
        )

    def _build_mt5_automation_risk_budget(self, operational_state, intent, orchestration) -> RiskBudgetAssessment:
        """Evaluate P40 only from observed operational counters; unknown stays blocked."""
        limits = RiskBudgetLimits(
            max_daily_loss=self.automation_risk_policy.max_daily_loss or 0.0,
            max_operations=self.automation_risk_policy.max_operations or 0,
        )
        if (
            operational_state is None
            or getattr(operational_state, "realized_loss_today", None) is None
            or getattr(operational_state, "trades_today", None) is None
        ):
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "perda realizada diária DEMO indisponível.")
        if limits.max_daily_loss <= 0 or limits.max_operations <= 0:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "orçamento P40 não está configurado com limites positivos.")
        proposed_loss = self.automation_risk_policy.max_loss_per_operation
        if proposed_loss is None:
            return RiskBudgetAssessment(BudgetDecision.BLOCKED, 0.0, 0, "perda máxima por operação não está configurada.")
        return RiskBudgetEvaluator().evaluate(
            RiskBudgetState(
                accumulated_loss=float(getattr(operational_state, "realized_loss_today")),
                operations_count=int(getattr(operational_state, "trades_today")),
            ),
            limits,
            proposed_loss,
        )

    @serialized_mt5_session
    def run_mt5_cycle(self, *, symbol: str, timeframe: str = "5m", limit: int = 100, amount: float = 0.01, duration_seconds: int = 60, senior_context=None) -> Any:
        """Run one unified DEMO runtime cycle from live MT5 observations."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol é obrigatório")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("timeframe é obrigatório")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
            raise ValueError("limit deve estar entre 20 e 500")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ValueError("amount deve ser um número válido em lotes")
        import math
        if not math.isfinite(float(amount)) or float(amount) <= 0:
            raise ValueError("amount deve ser finito e maior que zero")
        if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool) or not 1 <= duration_seconds <= 86400:
            raise ValueError("duration_seconds deve estar entre 1 e 86400")
        if self.trading_runtime is None or self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError(
                "ciclo MT5 DEMO exige CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo; "
                f"provider atual: {self.execution_provider!r}"
            )
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        state = self.mt5_operational_adapter.read_operational_state()
        return self.trading_runtime.run(
            request, operational_state=state, market_context=None, senior_context=senior_context,
            amount=amount, duration_seconds=duration_seconds, max_cycles=1,
            # The MT5 market adapter fetches only completed candles (start_pos=1).
            # These are server-derived facts, never client-supplied assertions.
            confirmed=True,
            # AdvancedFilters evaluates the actual candle-derived components.
            # Execution cycles always require those filters, even if a display/
            # analysis preference has been disabled by the user.
            filters_ok=True,
            filters_required=True,
            entry_conditions=(),
            checkpoint_store=self.operational_runtime.checkpoint_store,
            session_id=f"mt5-{symbol}-{timeframe}",
            automation_policy=AutomationPolicy(enabled=True, minimum_interval_seconds=0),
            automation_readiness_factory=self._build_mt5_automation_readiness,
            automation_risk_budget_factory=self._build_mt5_automation_risk_budget,
            automation_pretrade_risk_factory=self._build_mt5_pretrade_risk,
        )
    def schedule_mt5_timed_exit(self, cycle: Any, *, duration_seconds: int) -> dict[str, Any]:
        """Persist a best-effort DEMO exit only for an accepted, account-bound position."""
        from execution.execution_ledger import ExecutionLedgerStatus
        from execution.execution_lifecycle import ExecutionLifecycleState

        if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool) or not 1 <= duration_seconds <= 86400:
            raise ValueError("duration_seconds deve estar entre 1 e 86400")
        if self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        execution = getattr(cycle, "execution", None)
        plan = getattr(cycle, "plan", None)
        if execution is None or execution.accepted is not True or plan is None:
            return {"state": "NOT_APPLICABLE", "scheduled": False, "message": "nenhuma execução DEMO aceita neste ciclo"}
        request_id = getattr(plan, "request_id", None)
        if not isinstance(request_id, str) or not request_id.strip():
            return {"state": "BLOCKED", "scheduled": False, "message": "request_id ausente; saída temporizada bloqueada"}
        ledger = self.operational_runtime.execution_ledger
        identity = ledger.record_for(request_id)
        lifecycle = self.operational_runtime.execution_lifecycle.get(request_id)
        if (
            identity is None
            or identity.status not in (ExecutionLedgerStatus.ACCEPTED, ExecutionLedgerStatus.RECONCILED_EXECUTED)
            or lifecycle is None
            or lifecycle.state is not ExecutionLifecycleState.ACCEPTED
            or not identity.cycle_id
            or not identity.external_id
        ):
            return {"state": "BLOCKED", "scheduled": False, "message": "identidade persistida da execução DEMO incompleta"}
        fingerprint = identity.account_fingerprint
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 32
            or any(char not in "0123456789abcdef" for char in fingerprint)
        ):
            return {"state": "BLOCKED", "scheduled": False, "message": "identidade da conta de abertura ausente; saída temporizada bloqueada"}
        store = getattr(self.operational_runtime, "timed_exits", None)
        if store is None:
            return {"state": "BLOCKED", "scheduled": False, "message": "armazenamento persistente de saída temporizada indisponível"}
        try:
            record = store.schedule(
                request_id=request_id,
                cycle_id=identity.cycle_id,
                external_id=identity.external_id,
                account_fingerprint=fingerprint,
                delay_seconds=duration_seconds,
            )
        except Exception as exc:
            # The opening order may already be accepted. Do not disguise that
            # fact as a successful timed exit if local persistence failed.
            return {
                "state": "BLOCKED",
                "scheduled": False,
                "message": f"persistência da saída temporizada falhou ({type(exc).__name__}); fechamento manual explícito necessário",
            }
        return {
            "state": record.state,
            "scheduled": True,
            "request_id": record.request_id,
            "cycle_id": record.cycle_id,
            "external_id": record.external_id,
            "due_at": record.due_at.isoformat(),
            "best_effort": True,
            "message": "saída DEMO persistida; horário é alvo best-effort, não garantia de execução exata",
        }

    @serialized_mt5_session
    def analyze_mt5_market(
        self,
        *,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 100,
        confirmed: bool | None = None,
        filters_ok: bool | None = None,
    ) -> Any:
        """Analyze the current MT5 DEMO market snapshot without executing an order."""
        if confirmed is not None and not isinstance(confirmed, bool):
            raise ValueError("confirmed deve ser booleano ou None")
        if filters_ok is not None and not isinstance(filters_ok, bool):
            raise ValueError("filters_ok deve ser booleano ou None")
        if self.trading_runtime is None or self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError(
                "análise MT5 DEMO exige CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo; "
                f"provider atual: {self.execution_provider!r}"
            )
        symbol = str(symbol).strip()
        timeframe = str(timeframe).strip()
        if not symbol:
            raise ValueError("symbol é obrigatório")
        if not timeframe:
            raise ValueError("timeframe é obrigatório")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
            raise ValueError("limit deve estar entre 20 e 500")
        prefs = self.preferences.preferences
        effective_confirmed = prefs.require_closed_candle if confirmed is None else confirmed
        effective_filters = True if filters_ok is None else filters_ok
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        if self.trading_runtime.market_data_state is None:
            raise RuntimeError(
                "integridade dos dados de mercado não conectada; análise indisponível"
            )
        market_data_report = None
        try:
            operational_state = self.mt5_operational_adapter.read_operational_state()
            orchestration = self.trading_runtime.orchestrator.evaluate(
                request,
                operational_state=operational_state,
                market_context=None,
                confirmed=effective_confirmed,
                filters_ok=effective_filters,
                filters_required=prefs.require_filters,
            )
            if self.trading_runtime.market_data_state is not None:
                from core.p122_broker_market_data import BrokerMarketDataSnapshot
                market_data_report = self.trading_runtime.market_data_state.update(
                    BrokerMarketDataSnapshot(
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                        candles=tuple(orchestration.market_data.candles),
                        source=orchestration.market_data.source,
                        received_at=orchestration.timestamp,
                    ),
                    now=orchestration.timestamp,
                )
        except Exception as exc:
            # Never leave the previous successful market snapshot looking current.
            state = self.trading_runtime.market_data_state
            if state is not None:
                state.invalidate(f"ciclo de análise indisponível: {type(exc).__name__}")
            # Input validation above already ran before this try. A ValueError
            # here comes from the fetched market/runtime cycle, not the request.
            if isinstance(exc, ValueError):
                raise RuntimeError(
                    f"dados/contexto de mercado indisponíveis: {type(exc).__name__}"
                ) from exc
            raise
        if market_data_report is not None and not market_data_report.safe_for_analysis:
            # Keep the factual STALE/GAP/INVALID report for operational alerts,
            # but never return or persist a directional signal from unsafe data.
            raise RuntimeError(
                f"dados de mercado não seguros para análise: "
                f"{market_data_report.health.value}: {market_data_report.message}"
            )
        self._record_analysis(orchestration.analysis)
        return orchestration

    @serialized_mt5_session
    def replay_mt5_history(self, *, symbol: str, timeframe: str = "5m", limit: int = 100) -> dict[str, Any]:
        """Replay closed historical MT5 DEMO candles chronologically, without side effects."""
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError("Replay histórico exige provider IC Markets MT5 DEMO")
        symbol = str(symbol).strip()
        timeframe = str(timeframe).strip()
        if not symbol:
            raise ValueError("symbol é obrigatório")
        if not timeframe:
            raise ValueError("timeframe é obrigatório")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
            raise ValueError("limit deve estar entre 20 e 500")

        request = BrokerMarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        candles = tuple(self.mt5_market_adapter.fetch_market_data(request))
        if len(candles) < 2:
            raise RuntimeError("histórico insuficiente: são necessários pelo menos dois candles fechados")
        if any(candles[index].timestamp < candles[index - 1].timestamp for index in range(1, len(candles))):
            raise RuntimeError("histórico MT5 fora de ordem cronológica; replay bloqueado")

        records: list[dict[str, Any]] = []
        for index in range(1, len(candles)):
            prefix = candles[: index + 1]
            snapshot = BrokerMarketDataSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                candles=prefix,
                source="IC Markets MT5 DEMO · histórico fechado",
                received_at=prefix[-1].timestamp,
            )
            result = evaluate_candle_snapshot(snapshot)
            signal = result.signal.value
            records.append({
                "index": index + 1,
                "timestamp": prefix[-1].timestamp.isoformat(),
                "close": prefix[-1].close,
                "signal": signal,
                "score": result.score,
                "decision": "SINAL" if signal != Signal.AGUARDAR.value and result.confirmed else "AGUARDAR",
                "reason": result.reason,
            })

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "IC Markets MT5 DEMO",
            "candles_replayed": len(candles),
            "records": records,
            "buy_signals": sum(item["signal"] == Signal.COMPRA.value for item in records),
            "sell_signals": sum(item["signal"] == Signal.VENDA.value for item in records),
            "waiting": sum(item["decision"] == "AGUARDAR" for item in records),
            "orders_sent": False,
            "execution_allowed": False,
            "lookahead": False,
        }

    def simulate_mt5_signal_scenario(
        self,
        *,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 100,
        minimum_directional_score: int = 70,
    ) -> dict[str, Any]:
        """Evaluate a historical signal-threshold scenario; never simulate fills or P&L."""
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError("Simulador histórico exige provider IC Markets MT5 DEMO")
        symbol = str(symbol).strip()
        timeframe = str(timeframe).strip()
        if not symbol:
            raise ValueError("symbol é obrigatório")
        if not timeframe:
            raise ValueError("timeframe é obrigatório")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
            raise ValueError("limit deve estar entre 20 e 500")
        if (
            not isinstance(minimum_directional_score, int)
            or isinstance(minimum_directional_score, bool)
            or not 70 <= minimum_directional_score <= 95
        ):
            raise ValueError("minimum_directional_score deve estar entre 70 e 95")

        request = BrokerMarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        candles = tuple(self.mt5_market_adapter.fetch_market_data(request))
        if len(candles) < 2:
            raise RuntimeError("histórico insuficiente: são necessários pelo menos dois candles fechados")
        if any(
            candles[index].timestamp < candles[index - 1].timestamp
            for index in range(1, len(candles))
        ):
            raise RuntimeError("histórico MT5 fora de ordem cronológica; simulação bloqueada")
        if any(not candle.is_valid() for candle in candles):
            raise RuntimeError("histórico MT5 contém candle inválido; simulação bloqueada")

        records: list[dict[str, Any]] = []
        for index in range(1, len(candles)):
            prefix = candles[: index + 1]
            snapshot = BrokerMarketDataSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                candles=prefix,
                source="IC Markets MT5 DEMO · histórico fechado",
                received_at=prefix[-1].timestamp,
            )
            analysis = evaluate_candle_snapshot(snapshot)
            signal = analysis.signal.value
            directional_score = (
                float(analysis.score)
                if signal == Signal.COMPRA.value
                else 100.0 - float(analysis.score)
                if signal == Signal.VENDA.value
                else 0.0
            )
            if signal == Signal.AGUARDAR.value:
                outcome = "AGUARDAR"
                reason = analysis.reason
            elif directional_score < minimum_directional_score:
                outcome = "FILTRADO"
                reason = (
                    f"Score direcional hipotético {directional_score:.1f} abaixo do mínimo "
                    f"configurado de {minimum_directional_score}."
                )
            else:
                outcome = "CANDIDATO"
                reason = (
                    f"Sinal {signal} atende ao filtro hipotético de "
                    f"score direcional {minimum_directional_score}."
                )
            records.append({
                "index": index + 1,
                "timestamp": prefix[-1].timestamp.isoformat(),
                "close": prefix[-1].close,
                "signal": signal,
                "directional_score": round(directional_score, 2),
                "scenario": outcome,
                "reason": reason,
            })

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "IC Markets MT5 DEMO",
            "candles_replayed": len(candles),
            "minimum_directional_score": minimum_directional_score,
            "records": records,
            "candidates": sum(item["scenario"] == "CANDIDATO" for item in records),
            "filtered": sum(item["scenario"] == "FILTRADO" for item in records),
            "waiting": sum(item["scenario"] == "AGUARDAR" for item in records),
            "orders_sent": False,
            "execution_allowed": False,
            "pnl_calculated": False,
            "risk_rules_applied": False,
            "lookahead": False,
            "simulation_kind": "HISTORICAL_SIGNAL_THRESHOLD_ONLY",
        }

    @serialized_mt5_session
    def run_mt5_historical_backtest(
        self,
        *,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 200,
        stop_distance: float,
        take_profit_distance: float,
        quantity_units: float,
        contract_multiplier: float = 1.0,
        spread_price_units: float,
        slippage_price_units_per_side: float,
        commission_quote_per_unit_round_turn: float = 0.0,
        minimum_directional_score: int = 80,
    ) -> dict[str, Any]:
        """Run a deterministic, single-position OHLC backtest on closed MT5 DEMO bars."""
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError("Backtest histórico exige provider IC Markets MT5 DEMO")
        symbol = str(symbol).strip()
        timeframe = str(timeframe).strip()
        if not symbol or not timeframe:
            raise ValueError("symbol e timeframe são obrigatórios")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 20 <= limit <= 500:
            raise ValueError("limit deve estar entre 20 e 500")
        config = HistoricalBacktestConfig(
            stop_distance=stop_distance,
            take_profit_distance=take_profit_distance,
            quantity_units=quantity_units,
            contract_multiplier=contract_multiplier,
            spread_price_units=spread_price_units,
            slippage_price_units_per_side=slippage_price_units_per_side,
            commission_quote_per_unit_round_turn=commission_quote_per_unit_round_turn,
            minimum_directional_score=minimum_directional_score,
        )
        request = BrokerMarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        candles = tuple(self.mt5_market_adapter.fetch_market_data(request))
        if len(candles) < 20:
            raise RuntimeError("histórico insuficiente: são necessários pelo menos 20 candles fechados")
        if any(
            candles[index].timestamp <= candles[index - 1].timestamp
            for index in range(1, len(candles))
        ):
            raise RuntimeError("histórico MT5 fora de ordem ou com timestamps repetidos; backtest bloqueado")
        if any(not candle.is_valid() for candle in candles):
            raise RuntimeError("histórico MT5 contém candle inválido; backtest bloqueado")

        signals: list[HistoricalSignal] = []
        for index in range(len(candles)):
            prefix = candles[: index + 1]
            snapshot = BrokerMarketDataSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                candles=prefix,
                source="IC Markets MT5 DEMO · histórico fechado",
                received_at=prefix[-1].timestamp,
            )
            analysis = evaluate_candle_snapshot(snapshot)
            directional_score = (
                float(analysis.score)
                if analysis.signal is Signal.COMPRA
                else 100.0 - float(analysis.score)
                if analysis.signal is Signal.VENDA
                else 0.0
            )
            signals.append(HistoricalSignal(
                signal=analysis.signal,
                directional_score=directional_score,
                reason=analysis.reason,
            ))

        result = HistoricalTradeSimulator().run(
            candles=candles,
            signals=signals,
            config=config,
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "IC Markets MT5 DEMO",
            "quote_currency_note": "P&L expresso na moeda cotada do instrumento; não convertido para a moeda da conta.",
            "candles_processed": result.candles_processed,
            "candidates": result.candidates,
            "filtered": result.filtered,
            "waiting": result.waiting,
            "trades": [asdict(trade) for trade in result.trades],
            "trade_count": len(result.trades),
            "wins": result.wins,
            "losses": result.losses,
            "breakeven": result.breakeven,
            "win_rate": round(result.win_rate * 100, 2),
            "profit_factor": result.profit_factor,
            "gross_pnl_quote": result.gross_pnl_quote,
            "total_costs_quote": result.total_costs_quote,
            "net_pnl_quote": result.net_pnl_quote,
            "max_drawdown_quote": result.max_drawdown_quote,
            "max_consecutive_losses": result.max_consecutive_losses,
            "drawdown_note": "Drawdown absoluto em moeda cotada, calculado a partir de capital inicial zero; percentual não calculado porque saldo inicial não foi informado.",
            "assumptions": {
                "entry": "próxima abertura após o sinal no fechamento",
                "position_limit": "uma posição por vez",
                "stop_take_same_candle": "stop-loss primeiro, abordagem conservadora",
                "spread_price_units": config.spread_price_units,
                "slippage_price_units_per_side": config.slippage_price_units_per_side,
                "commission_quote_per_unit_round_turn": config.commission_quote_per_unit_round_turn,
                "quantity_units": config.quantity_units,
                "contract_multiplier": config.contract_multiplier,
                "stop_distance": config.stop_distance,
                "take_profit_distance": config.take_profit_distance,
                "minimum_directional_score": config.minimum_directional_score,
                "risk_manager_integrated": False,
                "margin_and_leverage_simulated": False,
                "account_currency_conversion": False,
            },
            "orders_sent": result.orders_sent,
            "execution_allowed": result.execution_allowed,
            "lookahead": result.lookahead,
            "simulation_kind": result.simulation_kind,
        }

    @serialized_mt5_session
    def get_mt5_assets(self, *, include_invisible: bool = False) -> tuple[dict[str, Any], ...]:
        """Return the broker-observed MT5 universe with session and 24/7 evidence."""
        if self.execution_provider != "ic_markets_mt5_demo":
            raise RuntimeError("catálogo MT5 exige provider IC Markets MT5 DEMO")
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("MetaTrader5 não está instalado") from exc
        if not self.mt5_market_adapter.initialize_terminal(mt5):
            raise RuntimeError("terminal MT5 configurado indisponível ou divergente")
        try:
            statuses = discover_mt5_instruments(mt5, include_invisible=include_invisible)
            assessments = {item.symbol: item for item in prioritize_mt5_assets(mt5, statuses)}
            result = []
            for status in statuses:
                assessment = assessments.get(status.symbol)
                result.append({
                    **asdict(status),
                    "is_24_7_capable": bool(status.weekend_capable),
                    "suitability": assessment.suitability.value if assessment else "INSUFFICIENT",
                    "suitability_evidence": list(assessment.evidence) if assessment else [],
                    "suitability_gaps": list(assessment.gaps) if assessment else [],
                    "suitability_rationale": assessment.rationale if assessment else "sem avaliação",
                    "source": "IC Markets MT5 DEMO",
                })
            return tuple(result)
        finally:
            mt5.shutdown()

    def validate_mt5_cycle_identity(self, *, cycle_id: str, external_id: str) -> None:
        """Validate the cycle/external binding before the MT5 close side effect."""
        if self.trading_runtime is None or self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        TradingRuntime.validate_external_cycle_identity(
            cycle_id=cycle_id,
            external_id=external_id,
            ledger=self.operational_runtime.execution_ledger,
            execution_lifecycle=self.operational_runtime.execution_lifecycle,
        )

    @staticmethod
    def _mt5_close_identity(*, operational_runtime, cycle_id: str, external_id: str):
        from core.trading_runtime import TradingRuntime
        from execution.execution_ledger import ExecutionLedgerStatus
        from execution.execution_lifecycle import ExecutionLifecycleState

        request_id, identity, execution_record = TradingRuntime.validate_external_cycle_identity(
            cycle_id=cycle_id,
            external_id=external_id,
            ledger=operational_runtime.execution_ledger,
            execution_lifecycle=operational_runtime.execution_lifecycle,
        )
        if identity.external_id != external_id.strip():
            raise ValueError("fechamento DEMO exige external_id já vinculado ao ciclo no ledger.")
        if identity.status not in (
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
        ):
            raise ValueError("somente posição DEMO com abertura confirmada pode ser fechada.")
        if execution_record.state is not ExecutionLifecycleState.ACCEPTED:
            raise ValueError("ciclo de abertura não está confirmado como ACCEPTED.")
        fingerprint = identity.account_fingerprint
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 32
            or any(char not in "0123456789abcdef" for char in fingerprint)
        ):
            raise ValueError("fechamento DEMO bloqueado: impressão digital da conta de abertura ausente ou inválida.")
        return request_id, fingerprint

    def list_mt5_position_recovery(self) -> list[dict[str, Any]]:
        """List accepted DEMO cycles needing operator recovery; never claims live OPEN state."""
        from execution.execution_ledger import ExecutionLedgerStatus
        from execution.execution_lifecycle import ExecutionLifecycleState
        from execution.position_close_store import PositionCloseState

        if self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        ledger = self.operational_runtime.execution_ledger
        lifecycle = self.operational_runtime.execution_lifecycle
        close_store = getattr(self.operational_runtime, "position_closes", None)
        if close_store is None:
            raise RuntimeError("armazenamento persistente de fechamento DEMO não configurado")

        results: list[dict[str, Any]] = []
        for request_id, identity in ledger.entries():
            if identity.status not in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ):
                continue
            if not identity.cycle_id or not identity.external_id:
                continue
            opening = lifecycle.get(request_id)
            if opening is None or opening.state is not ExecutionLifecycleState.ACCEPTED:
                continue
            fingerprint = identity.account_fingerprint
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 32
                or any(char not in "0123456789abcdef" for char in fingerprint)
            ):
                recovery_state = "BLOCKED_ACCOUNT_IDENTITY"
            else:
                close_record = close_store.get(request_id)
                if close_record is not None and close_record.state is PositionCloseState.CLOSED:
                    continue
                if close_record is not None and close_record.state is PositionCloseState.OPEN:
                    recovery_state = "BROKER_CONFIRMED_OPEN"
                else:
                    # This endpoint does not query MT5. OPEN must never be inferred
                    # merely because a cycle was accepted or a close was attempted.
                    recovery_state = "RECONCILIATION_REQUIRED"
            results.append({
                "cycle_id": identity.cycle_id,
                "external_id": identity.external_id,
                "recovery_state": recovery_state,
                "broker_query_performed": False,
                "order_sent": False,
            })
        return results

    def list_mt5_timed_exits(self) -> list[dict[str, Any]]:
        """Expose scheduled DEMO exit status without account secrets or broker actions."""
        if self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        store = getattr(self.operational_runtime, "timed_exits", None)
        if store is None:
            raise RuntimeError("armazenamento de saída temporizada indisponível")
        return [{
            "request_id": record.request_id,
            "cycle_id": record.cycle_id,
            "external_id": record.external_id,
            "due_at": record.due_at.isoformat(),
            "next_attempt_at": record.next_attempt_at.isoformat(),
            "state": record.state,
            "attempts": record.attempts,
            "message": record.message,
            "best_effort": True,
        } for record in store.records()]

    @serialized_mt5_session
    def close_mt5_position(self, *, cycle_id: str, external_id: str) -> Any:
        """Persist and close only the cycle's DEMO position on its original account."""
        from execution.ports import ExecutionResult
        from execution.position_close_store import PositionCloseState

        if self.operational_runtime is None or self.trading_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        store = getattr(self.operational_runtime, "position_closes", None)
        if store is None:
            raise RuntimeError("armazenamento persistente de fechamento DEMO não configurado")

        with self.operational_runtime.kill_switch.execution_lock():
            request_id, fingerprint = self._mt5_close_identity(
                operational_runtime=self.operational_runtime,
                cycle_id=cycle_id,
                external_id=external_id,
            )
            # Never dispatch a close from a stale UI observation. Query the
            # exact ticket/account immediately before the broker side effect.
            from execution.ports import PositionCloseObservation, PositionCloseObservationStatus
            observation = self.mt5_operational_adapter.reconcile_position_close(
                external_id.strip(),
                expected_account_fingerprint=fingerprint,
            )
            if (
                not isinstance(observation, PositionCloseObservation)
                or not isinstance(observation.status, PositionCloseObservationStatus)
                or not isinstance(observation.message, str)
            ):
                raise RuntimeError("adaptador retornou observação de posição DEMO inválida antes do fechamento")
            state_mapping = {
                PositionCloseObservationStatus.CLOSED: PositionCloseState.CLOSED,
                PositionCloseObservationStatus.OPEN: PositionCloseState.OPEN,
                PositionCloseObservationStatus.UNKNOWN: PositionCloseState.UNKNOWN,
            }
            current = store.get(request_id)
            if current is None:
                current = store.observe_initial(
                    request_id,
                    external_id.strip(),
                    state_mapping[observation.status],
                    message=observation.message,
                )
            elif current.state is not PositionCloseState.CLOSED:
                current = store.reconcile(
                    request_id,
                    state_mapping[observation.status],
                    message=observation.message,
                )
            if current.state is not PositionCloseState.OPEN:
                raise ValueError(
                    "fechamento DEMO bloqueado: a consulta MT5 mais recente não confirmou a posição OPEN"
                )
            store.begin(request_id, external_id.strip())
            try:
                close = self.mt5_operational_adapter.close_position(
                    external_id.strip(),
                    expected_account_fingerprint=fingerprint,
                )
            except Exception as exc:
                store.finish(
                    request_id,
                    PositionCloseState.UNKNOWN,
                    message=f"resultado do fechamento DEMO incerto após erro do adaptador: {type(exc).__name__}",
                )
                raise
            if not isinstance(close, ExecutionResult):
                store.finish(
                    request_id,
                    PositionCloseState.UNKNOWN,
                    message="adaptador retornou resultado de fechamento inválido",
                )
                raise RuntimeError("adaptador MT5 retornou resultado de fechamento inválido")
            store.finish(
                request_id,
                PositionCloseState.CLOSED if close.accepted else PositionCloseState.UNKNOWN,
                message=close.message,
                close_external_id=close.external_id if close.accepted else None,
            )
            return close

    @serialized_mt5_session
    def reconcile_mt5_position_close(self, *, cycle_id: str, external_id: str) -> dict[str, Any]:
        """Reconcile a DEMO close from broker evidence without sending another order."""
        from execution.ports import PositionCloseObservation, PositionCloseObservationStatus
        from execution.position_close_store import PositionCloseState

        if self.operational_runtime is None or self.trading_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        store = getattr(self.operational_runtime, "position_closes", None)
        if store is None:
            raise RuntimeError("armazenamento persistente de fechamento DEMO não configurado")

        with self.operational_runtime.kill_switch.execution_lock():
            request_id, fingerprint = self._mt5_close_identity(
                operational_runtime=self.operational_runtime,
                cycle_id=cycle_id,
                external_id=external_id,
            )
            record = store.get(request_id)
            if record is not None and record.external_id != external_id.strip():
                raise ValueError("tentativa de fechamento DEMO não encontrada para este ciclo/ticket")
            if record is None:
                # Initial inventory reconciliation is read-only; do not create
                # a fake close REQUESTED record before the operator asks to close.
                observation = self.mt5_operational_adapter.reconcile_position_close(
                    external_id.strip(),
                    expected_account_fingerprint=fingerprint,
                )
                if (
                    not isinstance(observation, PositionCloseObservation)
                    or not isinstance(observation.status, PositionCloseObservationStatus)
                    or not isinstance(observation.message, str)
                ):
                    raise RuntimeError("adaptador retornou observação de posição DEMO inválida")
                initial_mapping = {
                    PositionCloseObservationStatus.CLOSED: PositionCloseState.CLOSED,
                    PositionCloseObservationStatus.OPEN: PositionCloseState.OPEN,
                    PositionCloseObservationStatus.UNKNOWN: PositionCloseState.UNKNOWN,
                }
                resolved = store.observe_initial(
                    request_id,
                    external_id.strip(),
                    initial_mapping[observation.status],
                    message=observation.message,
                )
                return {
                    "request_id": resolved.request_id,
                    "external_id": resolved.external_id,
                    "state": resolved.state.value,
                    "message": resolved.message,
                    "read_only": True,
                    "order_sent": False,
                }
            if record.state is PositionCloseState.CLOSED:
                return {
                    "request_id": request_id,
                    "external_id": external_id.strip(),
                    "state": record.state.value,
                    "message": record.message,
                    "read_only": True,
                    "order_sent": False,
                }
            if record.state not in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN, PositionCloseState.OPEN):
                raise ValueError("estado de fechamento DEMO não pode ser reconciliado")

            observation = self.mt5_operational_adapter.reconcile_position_close(
                external_id.strip(),
                expected_account_fingerprint=fingerprint,
            )
            if (
                not isinstance(observation, PositionCloseObservation)
                or not isinstance(observation.status, PositionCloseObservationStatus)
                or not isinstance(observation.message, str)
            ):
                raise RuntimeError("adaptador retornou observação de fechamento DEMO inválida")
            mapping = {
                PositionCloseObservationStatus.CLOSED: PositionCloseState.CLOSED,
                PositionCloseObservationStatus.OPEN: PositionCloseState.OPEN,
                PositionCloseObservationStatus.UNKNOWN: PositionCloseState.UNKNOWN,
            }
            resolved = store.reconcile(
                request_id,
                mapping[observation.status],
                message=observation.message,
            )
            return {
                "request_id": resolved.request_id,
                "external_id": resolved.external_id,
                "state": resolved.state.value,
                "message": resolved.message,
                "read_only": True,
                "order_sent": False,
            }

    @serialized_mt5_session
    def reconcile_mt5_cycle(self, *, cycle_id: str, external_id: str) -> Any:
        """Reconcile one DEMO external order and close only its factual lifecycle."""
        if self.trading_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        return self.trading_runtime.reconcile_external_cycle(
            cycle_id=cycle_id,
            external_id=external_id,
            query_port=self.mt5_operational_adapter,
            ledger=self.operational_runtime.execution_ledger,
            execution_lifecycle=self.operational_runtime.execution_lifecycle,
        )

    def get_preferences(self) -> dict[str, Any]:
        value = self.preferences.preferences
        result = asdict(value)
        result["chart_theme"] = value.chart_theme.value
        result["candle"]["style"] = value.candle.style.value
        result["candle"]["color_mode"] = value.candle.color_mode.value
        return result

    def update_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        changes = dict(payload)
        if "chart_theme" in changes and isinstance(changes["chart_theme"], str):
            changes["chart_theme"] = ChartTheme(changes["chart_theme"].upper())
        self.preferences.update(**changes)
        self.state_store.save_preferences(self.preferences.preferences)
        return self.get_preferences()

    def update_candle_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        changes = dict(payload)
        from core.ecosystem_preferences import CandleColorMode, CandleStyle
        if "style" in changes and isinstance(changes["style"], str):
            changes["style"] = CandleStyle(changes["style"].upper())
        if "color_mode" in changes and isinstance(changes["color_mode"], str):
            changes["color_mode"] = CandleColorMode(changes["color_mode"].upper())
        self.preferences.update_candle(**changes)
        self.state_store.save_preferences(self.preferences.preferences)
        return self.get_preferences()

    def update_notification_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update_notifications(**dict(payload))
        self.state_store.save_preferences(self.preferences.preferences)
        return self.get_preferences()

    def _notification_visible(self, item: EcosystemNotification) -> bool:
        prefs = self.preferences.preferences.notifications
        if item.severity is NotificationSeverity.CRITICAL:
            return True
        if item.severity is NotificationSeverity.INFO:
            return prefs.info_enabled
        if not prefs.important_enabled:
            return False
        category_enabled = {
            NotificationKind.SYSTEM_UPDATE: prefs.system_updates_enabled,
            NotificationKind.SECURITY: prefs.security_enabled,
            NotificationKind.MARKET: prefs.market_enabled,
            NotificationKind.RISK: prefs.risk_enabled,
            NotificationKind.CONNECTION: prefs.connection_enabled,
            NotificationKind.EXECUTION: prefs.execution_enabled,
            NotificationKind.LEARNING: prefs.learning_enabled,
            NotificationKind.RECOVERY: prefs.recovery_enabled,
        }[item.kind]
        return category_enabled

    def _visible_notifications(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        events = self.notifications.visible(include_info=include_info)
        return tuple(item for item in events if self._notification_visible(item))

    def _operational_notifications(self) -> list[dict[str, Any]]:
        """Expose current operational and audit incidents without granting authority."""
        kind_by_source = {
            "execution": NotificationKind.EXECUTION,
            "recovery": NotificationKind.RECOVERY,
            "reconciliation": NotificationKind.RECOVERY,
            "market_data": NotificationKind.MARKET,
            "runtime_health": NotificationKind.SYSTEM_UPDATE,
            "kill_switch": NotificationKind.RISK,
            "security_audit": NotificationKind.SECURITY,
            "notifications": NotificationKind.SECURITY,
        }
        severity_by_incident = {
            "CRITICAL": NotificationSeverity.CRITICAL,
            "WARNING": NotificationSeverity.IMPORTANT,
        }
        incidents = (
            build_operational_incidents(self.operational_observability())
            if self.operational_runtime is not None
            else []
        )
        # A failed audit database is a security incident even when the trading
        # runtime is disconnected. An intentionally unconfigured optional DB
        # is not a failure and must not create a false critical notification.
        if not AUDIT.persistence_available and AUDIT.persistence_error is not None:
            incidents.append(
                OperationalIncident(
                    code="SECURITY_AUDIT_PERSISTENCE_FAILED",
                    severity="CRITICAL",
                    status=str(AUDIT.persistence_error).upper(),
                    source="security_audit",
                    message="persistência da trilha de auditoria indisponível; verifique o armazenamento local",
                )
            )
        notification_store_error = self.state_store.notifications_load_error
        if notification_store_error is None and self.notifications.restore_had_invalid_records:
            notification_store_error = "invalid_records"
        if notification_store_error is not None:
            incidents.append(
                OperationalIncident(
                    code="NOTIFICATION_STORE_CORRUPT",
                    severity="CRITICAL",
                    status=str(notification_store_error).upper(),
                    source="notifications",
                    message="O histórico persistido de notificações está corrompido; registros inválidos não foram restaurados.",
                )
            )
        items: list[dict[str, Any]] = []
        for incident in incidents:
            severity = severity_by_incident.get(incident.severity.upper(), NotificationSeverity.IMPORTANT)
            items.append(
                {
                    "notification_id": f"operational-{incident.code}",
                    "kind": kind_by_source.get(incident.source, NotificationKind.SYSTEM_UPDATE).value,
                    "severity": severity.value,
                    "title": incident.code,
                    "status": incident.status,
                    "message": incident.message,
                    "requires_attention": severity is NotificationSeverity.CRITICAL,
                    "blocking": severity is NotificationSeverity.CRITICAL,
                }
            )
        return items

    def notification_summary(self) -> dict[str, Any]:
        persisted = [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self._visible_notifications(include_info=False)]
        items = persisted + self._operational_notifications()
        return {
            "count": len(items),
            "critical_count": sum(1 for item in items if item["severity"] == NotificationSeverity.CRITICAL.value),
            "items": items,
            # Compatibility contract for the native MT5 panel.
            "notifications": items,
            "total": len(items),
            "unread": sum(1 for item in items if item.get("requires_attention", False)),
            "execution_allowed": False,
        }

    def all_notifications(self) -> list[dict[str, Any]]:
        persisted = [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self.notifications.all()]
        return persisted + self._operational_notifications()

    def publish_ecosystem_update(self, title: str, message: str, *, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> dict[str, Any]:
        notification_id = f"update-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish_update(notification_id, title, message, important=True, update_kind=update_kind)
        self.state_store.save_notifications([asdict(notification) | {"kind": notification.kind.value, "severity": notification.severity.value} for notification in self.notifications.all()])
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Route a material runtime event into the notification center."""
        notification_kind = NotificationKind(str(kind).upper())
        severity = NotificationSeverity.CRITICAL if critical else NotificationSeverity.IMPORTANT
        notification_id = f"event-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish(EcosystemNotification(notification_id, notification_kind, severity, title, message, requires_attention=critical or blocking, blocking=blocking))
        self.state_store.save_notifications([asdict(notification) | {"kind": notification.kind.value, "severity": notification.severity.value} for notification in self.notifications.all()])
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
