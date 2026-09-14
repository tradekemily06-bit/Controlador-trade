from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from core.ecosystem_maintenance import MaintenanceManager
from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from core.models import AnalysisResult, Signal
from core.senior_analysis_gate import SeniorAnalysisGate
from core.trading_psychology import PsychologyCheckIn, TradingPsychologyGuard
from core.trading_psychology_advanced import AdvancedTradingPsychology, BehavioralObservation
from integration.ecosystem_service import EcosystemService
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary
from integration.p137_operational_risk_bridge import OperationalRiskBridge


class ConfiguredEcosystemService(EcosystemService):
    """Ecosystem service with preferences, notifications and senior analysis wired in."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.preferences = EcosystemPreferencesStore()
        self.notifications = EcosystemNotificationCenter()
        self.maintenance = MaintenanceManager()
        self.psychology = TradingPsychologyGuard()
        self.advanced_psychology = AdvancedTradingPsychology()
        self.senior_analysis_gate = SeniorAnalysisGate()
        self.operational_risk_bridge = OperationalRiskBridge(self.risk)

    def analyze(self, payload: dict[str, Any], *, persist: bool = True, subject_id: str | None = None, tenant_id: str | None = None):
        """Require senior context and operational risk for actionable analysis."""
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        try:
            context_input = SeniorAnalysisBoundary.build_input(payload)
        except ValueError as exc:
            safe = AnalysisResult(signal=Signal.AGUARDAR, score=float(payload.get("score", 0)), reason=f"Análise sênior não pode ser concluída: {exc}.", confirmed=False, symbol=payload.get("symbol"), timeframe=payload.get("timeframe"))
            return self._record_analysis(safe, persist=persist, owner=owner)
        senior_context = self.senior_context.assess(context_input)
        candidate = self.engine.evaluate(score=payload.get("score", 50), confirmed=payload.get("confirmed", False), filters_ok=payload.get("filters_ok", True), symbol=payload.get("symbol"), timeframe=payload.get("timeframe"))
        operational_risk = self.operational_risk_bridge.evaluate(payload)
        gated = self.senior_analysis_gate.evaluate(analysis=candidate, senior_context=senior_context, operational_risk=operational_risk)
        return self._record_analysis(gated, persist=persist, owner=owner)

    def _record_analysis(self, result, *, persist: bool = True, owner=None):
        from analysis.decision_record import DecisionRecord
        record = DecisionRecord.from_analysis(result)
        if owner is not None:
            record = record.with_owner(subject_id=owner.subject_id, tenant_id=owner.tenant_id)
        if persist:
            self._persist_records([record])
        return record

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
        category_enabled = {NotificationKind.SYSTEM_UPDATE: prefs.system_updates_enabled, NotificationKind.SECURITY: prefs.security_enabled, NotificationKind.MARKET: prefs.market_enabled, NotificationKind.RISK: prefs.risk_enabled, NotificationKind.CONNECTION: prefs.connection_enabled, NotificationKind.EXECUTION: prefs.execution_enabled, NotificationKind.LEARNING: prefs.learning_enabled, NotificationKind.RECOVERY: prefs.recovery_enabled}[item.kind]
        return category_enabled

    def _visible_notifications(self, *, include_info: bool = False) -> tuple[EcosystemNotification, ...]:
        events = self.notifications.visible(include_info=include_info)
        return tuple(item for item in events if self._notification_visible(item))

    def notification_summary(self) -> dict[str, Any]:
        visible = self._visible_notifications(include_info=False)
        return {"count": len(visible), "critical_count": len(self.notifications.critical()), "items": [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in visible]}

    def all_notifications(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"kind": item.kind.value, "severity": item.severity.value} for item in self.notifications.all()]

    def publish_ecosystem_update(self, title: str, message: str, *, update_kind: UpdateKind = UpdateKind.ECOSYSTEM) -> dict[str, Any]:
        notification_id = f"update-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish_update(notification_id, title, message, important=True, update_kind=update_kind)
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def schedule_maintenance(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Announce planned downtime before an update begins."""
        starts_at = datetime.fromisoformat(str(payload.get("starts_at", "")).replace("Z", "+00:00"))
        window = self.maintenance.schedule(maintenance_id=str(payload.get("maintenance_id", "")), title=str(payload.get("title", "Atualização programada")), message=str(payload.get("message", "O ecossistema ficará temporariamente indisponível para atualização.")), starts_at=starts_at, duration_minutes=int(payload.get("duration_minutes", 1)))
        notice = window.user_notice()
        self.publish_material_event("SYSTEM_UPDATE", notice["title"], f"{notice['message']} Início: {notice['starts_at']}. Retorno previsto: {notice['expected_return_at']} ({notice['duration_minutes']} min).", critical=True, blocking=False)
        return notice

    def maintenance_status(self) -> dict[str, Any]:
        return self.maintenance.status()

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        """Route a material runtime event into the notification center."""
        notification_kind = NotificationKind(str(kind).upper())
        severity = NotificationSeverity.CRITICAL if critical else NotificationSeverity.IMPORTANT
        notification_id = f"event-{len(self.notifications.all()) + 1}"
        item = self.notifications.publish(EcosystemNotification(notification_id, notification_kind, severity, title, message, requires_attention=critical or blocking, blocking=blocking))
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def psychology_check_in(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return behavioral self-awareness feedback; never authorizes trading."""
        if not self.preferences.preferences.psychology_enabled:
            return {"enabled": False, "flags": [], "risk_level": "DISABLED", "message": "Psicologia do trader está desativada nas preferências.", "suggested_action": None, "trading_authorized": False}
        check_in = PsychologyCheckIn(emotional_state=str(payload.get("emotional_state", "")), urge_to_trade=int(payload.get("urge_to_trade", 0)), recent_losses=int(payload.get("recent_losses", 0)), fatigue=int(payload.get("fatigue", 0)), confidence=int(payload.get("confidence", 0)), rule_adherence=int(payload.get("rule_adherence", 0)))
        assessment = self.psychology.assess(check_in)
        return {"enabled": True, "flags": [flag.value for flag in assessment.flags], "risk_level": assessment.risk_level, "message": assessment.message, "suggested_action": assessment.suggested_action, "trading_authorized": False}

    def advanced_psychology_assessment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Assess observable trader behavior with advanced, explainable guardrails."""
        if not self.preferences.preferences.psychology_enabled:
            return {"enabled": False, "patterns": [], "severity": "DISABLED", "score": 0, "evidence": [], "intervention": None, "learning_focus": [], "execution_authorized": False}
        observation = BehavioralObservation(
            operations=int(payload.get("operations", 0)),
            losses=int(payload.get("losses", 0)),
            consecutive_losses=int(payload.get("consecutive_losses", 0)),
            seconds_since_last_operation=payload.get("seconds_since_last_operation"),
            risk_per_operation=float(payload.get("risk_per_operation", 0.0)),
            baseline_risk=float(payload.get("baseline_risk", 0.0)),
            rules_broken=int(payload.get("rules_broken", 0)),
            repeated_same_setup=int(payload.get("repeated_same_setup", 0)),
            hesitation_count=int(payload.get("hesitation_count", 0)),
            revenge_intent=bool(payload.get("revenge_intent", False)),
            urgency=int(payload.get("urgency", 0)),
            fatigue=int(payload.get("fatigue", 0)),
            confidence=int(payload.get("confidence", 5)),
            plan_adherence=int(payload.get("plan_adherence", 10)),
            post_loss_risk_change=float(payload.get("post_loss_risk_change", 0.0)),
            recent_win_streak=int(payload.get("recent_win_streak", 0)),
            recent_loss_streak=int(payload.get("recent_loss_streak", 0)),
        )
        profile = self.advanced_psychology.assess(observation)
        return {"enabled": True, "patterns": [item.value for item in profile.patterns], "severity": profile.severity, "score": profile.score, "evidence": list(profile.evidence), "intervention": profile.intervention, "learning_focus": list(profile.learning_focus), "execution_authorized": False}
