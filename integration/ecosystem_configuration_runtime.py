from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from core.ecosystem_maintenance import MaintenanceManager
from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity, UpdateKind
from core.ecosystem_preferences import ChartTheme, EcosystemPreferencesStore
from core.models import AnalysisResult, Signal
from core.scoped_learning_state import ScopedLearningState
from core.senior_analysis_gate import SeniorAnalysisGate
from core.trading_psychology import PsychologyCheckIn, TradingPsychologyGuard
from core.advanced_trading_psychology import AdvancedTradingPsychology, TradingBehaviorSnapshot
from core.trading_psychology_history import TradingPsychologyHistory
from integration.ecosystem_service import EcosystemService
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary
from integration.p137_operational_risk_bridge import OperationalRiskBridge
from integration.production_scoped_service import ProductionScopedServiceMixin
from security.http_identity import current_trusted_identity, saas_public_mode


class ConfiguredEcosystemService(ProductionScopedServiceMixin, EcosystemService):
    """Ecosystem service with scoped durable production state wired in."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        state_store = self.production_data_plane.state_store if self.production_data_plane is not None else None
        self.preferences = EcosystemPreferencesStore(state_store=state_store)
        self.notifications = EcosystemNotificationCenter(state_store=state_store, require_durable=saas_public_mode())
        self.maintenance = self.operational_runtime.maintenance if self.operational_runtime is not None else MaintenanceManager()
        self.psychology = TradingPsychologyGuard()
        self.advanced_psychology = AdvancedTradingPsychology()
        self.psychology_history = TradingPsychologyHistory(self.advanced_psychology)
        self.senior_analysis_gate = SeniorAnalysisGate()
        if self.operational_runtime is not None:
            from core.operational_barrier_factory import build_global_operational_barrier
            self.operational_risk_bridge = OperationalRiskBridge(
                self.risk,
                incident_manager=self.operational_runtime.incident_manager,
                operational_barrier_provider=lambda: build_global_operational_barrier(self.operational_runtime),
                operational_state_provider=self.operational_runtime.risk_state_provider,
            )
        else:
            # No runtime means the bridge remains deliberately fail-closed.
            self.operational_risk_bridge = OperationalRiskBridge(self.risk)
        self.scoped_learning = ScopedLearningState(state_store=state_store, require_durable=saas_public_mode())

    def _owner_context(self, *, subject_id: str | None, tenant_id: str | None):
        identity = current_trusted_identity()
        if subject_id is None and tenant_id is None and identity is not None:
            subject_id, tenant_id = identity.subject_id, identity.tenant_id
        return super()._owner_context(subject_id=subject_id, tenant_id=tenant_id)

    def _psychology_owner(self):
        identity = current_trusted_identity()
        if identity is not None:
            return self._owner_context(subject_id=identity.subject_id, tenant_id=identity.tenant_id)
        if saas_public_mode():
            raise PermissionError("trusted scope is required for psychology history")
        return None

    def _learning_scope(self):
        identity = current_trusted_identity()
        if identity is None:
            if saas_public_mode():
                raise PermissionError("trusted scope is required for learning state")
            return None
        return self.scoped_learning.get(tenant_id=identity.tenant_id, subject_id=identity.subject_id)

    def _persist_learning_scope(self) -> None:
        identity = current_trusted_identity()
        if identity is None:
            if saas_public_mode():
                raise PermissionError("trusted scope is required for learning state")
            return
        self.scoped_learning.persist(tenant_id=identity.tenant_id, subject_id=identity.subject_id)

    def analyze(self, payload: dict[str, Any], *, persist: bool = True, subject_id: str | None = None, tenant_id: str | None = None):
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
        notification_id = self.notifications.new_id("update")
        item = self.notifications.publish_update(notification_id, title, message, important=True, update_kind=update_kind)
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def schedule_maintenance(self, payload: dict[str, Any]) -> dict[str, Any]:
        starts_at = datetime.fromisoformat(str(payload.get("starts_at", "")).replace("Z", "+00:00"))
        window = self.maintenance.schedule(maintenance_id=str(payload.get("maintenance_id", "")), title=str(payload.get("title", "Atualização programada")), message=str(payload.get("message", "O ecossistema ficará temporariamente indisponível para atualização.")), starts_at=starts_at, duration_minutes=int(payload.get("duration_minutes", 1)))
        notice = window.user_notice()
        self.publish_material_event("SYSTEM_UPDATE", notice["title"], f"{notice['message']} Início: {notice['starts_at']}. Retorno previsto: {notice['expected_return_at']} ({notice['duration_minutes']} min).", critical=True, blocking=False)
        return notice

    def maintenance_status(self) -> dict[str, Any]:
        return self.maintenance.status()

    def publish_material_event(self, kind: str, title: str, message: str, *, critical: bool = False, blocking: bool = False) -> dict[str, Any]:
        notification_kind = NotificationKind(str(kind).upper())
        severity = NotificationSeverity.CRITICAL if critical else NotificationSeverity.IMPORTANT
        notification_id = self.notifications.new_id("event")
        item = self.notifications.publish(EcosystemNotification(notification_id, notification_kind, severity, title, message, requires_attention=critical or blocking, blocking=blocking))
        return asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}

    def psychology_check_in(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.preferences.preferences.psychology_enabled:
            return {"enabled": False, "flags": [], "risk_level": "DISABLED", "message": "Psicologia do trader está desativada nas preferências.", "suggested_action": None, "trading_authorized": False}
        check_in = PsychologyCheckIn(emotional_state=str(payload.get("emotional_state", "")), urge_to_trade=int(payload.get("urge_to_trade", 0)), recent_losses=int(payload.get("recent_losses", 0)), fatigue=int(payload.get("fatigue", 0)), confidence=int(payload.get("confidence", 0)), rule_adherence=int(payload.get("rule_adherence", 0)))
        assessment = self.psychology.assess(check_in)
        return {"enabled": True, "flags": [flag.value for flag in assessment.flags], "risk_level": assessment.risk_level, "message": assessment.message, "suggested_action": assessment.suggested_action, "trading_authorized": False}

    def advanced_psychology_assessment(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.preferences.preferences.psychology_enabled:
            return {"enabled": False, "patterns": [], "risk_level": "DISABLED", "score": 0, "evidence": [], "recommendations": [], "trading_authorized": False}
        snapshot = TradingBehaviorSnapshot(
            trades_count=int(payload.get("trades_count", payload.get("operations", 0))), losses=int(payload.get("losses", 0)), wins=int(payload.get("wins", 0)), consecutive_losses=int(payload.get("consecutive_losses", 0)), avg_seconds_between_trades=payload.get("avg_seconds_between_trades", payload.get("seconds_since_last_operation")), risk_before=payload.get("risk_before", payload.get("baseline_risk")), risk_after=payload.get("risk_after", payload.get("risk_per_operation")), rule_breaks=int(payload.get("rule_breaks", payload.get("rules_broken", 0))), impulsive_entries=int(payload.get("impulsive_entries", 0)), avoided_valid_setups=int(payload.get("avoided_valid_setups", 0)), repeated_entries_after_loss=int(payload.get("repeated_entries_after_loss", payload.get("repeated_same_setup", 0))), confirmation_requests=int(payload.get("confirmation_requests", 0)), fatigue=int(payload.get("fatigue", 0)), urge_to_trade=int(payload.get("urge_to_trade", payload.get("urgency", 0))), confidence=int(payload.get("confidence", 0)), emotional_state=str(payload.get("emotional_state", "")))
        assessment = self.advanced_psychology.assess(snapshot)
        result = {"enabled": True, "patterns": [item.pattern.value for item in assessment.evidence], "risk_level": assessment.risk_level, "score": assessment.score, "evidence": [{"pattern": item.pattern.value, "severity": item.severity, "evidence": list(item.evidence), "recommendation": item.recommendation} for item in assessment.evidence], "recommendations": list(assessment.recommendations), "trading_authorized": False}
        if self.preferences.preferences.psychology_data_collection_enabled:
            owner = self._psychology_owner()
            history = self._scoped_memory(owner)
            historical = self.psychology_history.assess_history(history)
            result["history"] = {"score": historical.score, "risk_level": historical.risk_level, "patterns": [item.pattern.value for item in historical.evidence], "recommendations": list(historical.recommendations), "trading_authorized": False}
        else:
            result["history"] = {"enabled": False, "reason": "behavioral data collection is disabled"}
        return result

    def psychology_status(self) -> dict[str, Any]:
        prefs = self.preferences.preferences
        return {"enabled": prefs.psychology_enabled, "data_collection_enabled": prefs.psychology_data_collection_enabled, "execution_authority": False, "decision_authority": False, "role": "parallel_behavioral_protection"}

    def screen_learning_source(self, payload: dict[str, Any]):
        scope = self._learning_scope()
        if scope is None:
            return super().screen_learning_source(payload)
        source_type = __import__("core.p128_learning_source_gate", fromlist=["LearningSourceType"]).LearningSourceType(str(payload.get("source_type", "LINK")).upper())
        source = self.learning_source_gate.intake(source_id=str(payload.get("source_id", "")), source_type=source_type, uri=str(payload.get("uri", "")))
        if source.source_id in scope.sources:
            raise ValueError("source_id já cadastrado")
        scope.sources[source.source_id] = source
        self._persist_learning_scope()
        return source

    def validate_learning_source(self, source, *, content_verified: bool, security_checked: bool):
        scope = self._learning_scope()
        if scope is None:
            return super().validate_learning_source(source, content_verified=content_verified, security_checked=security_checked)
        current = scope.sources.get(source.source_id)
        if current is None:
            raise ValueError("source_id não encontrado no tenant atual")
        updated = self.learning_source_gate.validate_content(current, content_verified=content_verified, security_checked=security_checked)
        scope.sources[updated.source_id] = updated
        self._persist_learning_scope()
        return updated

    def admit_learning_knowledge(self, source, *, knowledge_validated: bool):
        scope = self._learning_scope()
        if scope is None:
            return super().admit_learning_knowledge(source, knowledge_validated=knowledge_validated)
        current = scope.sources.get(source.source_id)
        if current is None:
            raise ValueError("source_id não encontrado no tenant atual")
        updated = self.learning_source_gate.admit_knowledge(current, knowledge_validated=knowledge_validated)
        scope.sources[updated.source_id] = updated
        self._persist_learning_scope()
        return updated

    def learning_sources_view(self):
        scope = self._learning_scope()
        if scope is None:
            return super().learning_sources_view()
        return [asdict(item) | {"source_type": item.source_type.value, "status": item.status.value} for item in scope.sources.values()]

    def add_learning_resource(self, payload: dict[str, Any]):
        scope = self._learning_scope()
        if scope is None:
            return super().add_learning_resource(payload)
        resource = __import__("core.learning_content", fromlist=["LearningResource", "ContentType", "LearningStatus", "normalize_tags"])
        item = resource.LearningResource(resource_id=str(payload.get("resource_id", "")), title=str(payload.get("title", "")), content_type=resource.ContentType(str(payload.get("content_type", "OTHER")).upper()), source_url=payload.get("source_url"), source_name=payload.get("source_name"), status=resource.LearningStatus(str(payload.get("status", "RECEIVED")).upper()), tags=resource.normalize_tags(tuple(payload.get("tags", ()) or ())))
        if item.resource_id in scope.resources:
            raise ValueError("resource_id já cadastrado")
        if item.source_url:
            from urllib.parse import urlparse
            parsed = urlparse(item.source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("source_url inválida")
        scope.resources[item.resource_id] = item
        self._persist_learning_scope()
        return item
