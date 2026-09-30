from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine
from core.live_orchestrator import TradingOrchestrator
from core.signal_quality import SignalQualityEvaluator
from core.trading_runtime import TradingRuntime
from data.feed import MarketDataFeed, MarketDataRequest
from core.execution_coordinator import ExecutionCoordinator
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from core.models import AnalysisResult, Signal
from core.senior_analysis_gate import SeniorAnalysisGate
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from integration.ecosystem_service import EcosystemService
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary
from integration.p137_operational_risk_bridge import OperationalRiskBridge


class ConfiguredEcosystemService(EcosystemService):
    """Ecosystem service with preferences, notifications and senior analysis wired in."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.preferences = EcosystemPreferencesStore()
        self.notifications = EcosystemNotificationCenter()
        self.senior_analysis_gate = SeniorAnalysisGate()
        self.operational_risk_bridge = OperationalRiskBridge(self.risk)
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

    def run_mt5_cycle(self, *, symbol: str, timeframe: str = "5m", limit: int = 100, amount: float = 0.01, duration_seconds: int = 60, senior_context=None, confirmed: bool = False, filters_ok: bool = True, entry_conditions: tuple[str, ...] = ()) -> Any:
        """Run one unified DEMO runtime cycle from live MT5 observations."""
        if self.trading_runtime is None or self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        request = MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit)
        state = self.mt5_operational_adapter.read_operational_state()
        return self.trading_runtime.run(
            request, operational_state=state, market_context=None, senior_context=senior_context,
            amount=amount, duration_seconds=duration_seconds, max_cycles=1,
            confirmed=confirmed, filters_ok=filters_ok, entry_conditions=entry_conditions,
            checkpoint_store=self.operational_runtime.checkpoint_store,
            session_id=f"mt5-{symbol}-{timeframe}",
        )
    def reconcile_mt5_cycle(self, *, cycle_id: str, external_id: str) -> Any:
        """Reconcile one DEMO external order and close only its factual lifecycle."""
        if self.trading_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        return self.trading_runtime.reconcile_external_cycle(
            cycle_id=cycle_id,
            external_id=external_id,
            query_port=self.mt5_operational_adapter,
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
        return self.get_preferences()

    def update_candle_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        changes = dict(payload)
        from core.ecosystem_preferences import CandleColorMode, CandleStyle
        if "style" in changes and isinstance(changes["style"], str):
            changes["style"] = CandleStyle(changes["style"].upper())
        if "color_mode" in changes and isinstance(changes["color_mode"], str):
            changes["color_mode"] = CandleColorMode(changes["color_mode"].upper())
        self.preferences.update_candle(**changes)
        return self.get_preferences()

    def update_notification_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.preferences.update_notifications(**dict(payload))
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

    def notification_summary(self) -> dict[str, Any]:
        visible = self._visible_notifications(include_info=False)
        return {
            "count": len(visible),
            "critical_count": len(self.notifications.critical()),
            "items": [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in visible],
        }

    def all_notifications(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self.notifications.all()]

    def publish_ecosystem_update(self, title: str, message: str, *, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> dict[str, Any]:
        notification_id = f"update-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish_update(notification_id, title, message, important=True, update_kind=update_kind)
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Route a material runtime event into the notification center."""
        notification_kind = NotificationKind(str(kind).upper())
        severity = NotificationSeverity.CRITICAL if critical else NotificationSeverity.IMPORTANT
        notification_id = f"event-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish(EcosystemNotification(notification_id, notification_kind, severity, title, message, requires_attention=critical or blocking, blocking=blocking))
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
