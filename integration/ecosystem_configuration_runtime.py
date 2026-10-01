from __future__ import annotations

from dataclasses import asdict
from typing import Any
from pathlib import Path
import tempfile

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from core.operational_alerts import build_operational_incidents
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
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from core.ecosystem_state_store import EcosystemStateStore
from core.models import AnalysisResult, Signal
from core.senior_analysis_gate import SeniorAnalysisGate
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from integration.ecosystem_service import EcosystemService
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary
from integration.p137_operational_risk_bridge import OperationalRiskBridge


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

    def run_mt5_cycle(self, *, symbol: str, timeframe: str = "5m", limit: int = 100, amount: float = 0.01, duration_seconds: int = 60, senior_context=None, confirmed: bool = False, filters_ok: bool = True, entry_conditions: tuple[str, ...] = ()) -> Any:
        """Run one unified DEMO runtime cycle from live MT5 observations."""
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
            confirmed=confirmed, filters_ok=filters_ok, entry_conditions=entry_conditions,
            checkpoint_store=self.operational_runtime.checkpoint_store,
            session_id=f"mt5-{symbol}-{timeframe}",
            automation_policy=AutomationPolicy(enabled=True, minimum_interval_seconds=0),
            automation_readiness_factory=self._build_mt5_automation_readiness,
            automation_risk_budget_factory=self._build_mt5_automation_risk_budget,
            automation_pretrade_risk_factory=self._build_mt5_pretrade_risk,
        )
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

    def close_mt5_position(self, *, external_id: str) -> Any:
        """Close only the identified DEMO position through the existing MT5 safety boundary."""
        return self.mt5_operational_adapter.close_position(external_id)

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
        """Expose current runtime incidents through the notification channel."""
        kind_by_source = {
            "execution": NotificationKind.EXECUTION,
            "recovery": NotificationKind.RECOVERY,
            "reconciliation": NotificationKind.RECOVERY,
            "market_data": NotificationKind.MARKET,
            "runtime_health": NotificationKind.SYSTEM_UPDATE,
            "kill_switch": NotificationKind.RISK,
        }
        severity_by_incident = {
            "CRITICAL": NotificationSeverity.CRITICAL,
            "WARNING": NotificationSeverity.IMPORTANT,
        }
        items: list[dict[str, Any]] = []
        for incident in build_operational_incidents(self.operational_observability()):
            severity = severity_by_incident.get(incident.severity.upper(), NotificationSeverity.IMPORTANT)
            items.append(
                {
                    "notification_id": f"operational-{incident.code}",
                    "kind": kind_by_source.get(incident.source, NotificationKind.SYSTEM_UPDATE).value,
                    "severity": severity.value,
                    "title": incident.code,
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
