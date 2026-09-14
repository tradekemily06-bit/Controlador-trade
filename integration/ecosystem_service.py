from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from core.ecosystem_health import build_health_alerts
from core.ecosystem_maintenance import MaintenanceStatus
from core.ecosystem_notifications import NotificationSeverity
from core.ecosystem_preferences import EcosystemPreferencesStore
from core.learning_content import ContentType, LearningActivity, LearningAttempt, LearningObservation, LearningResource, LearningStatus, normalize_tags
from core.market_data_runtime_integrity import MarketDataRuntimeReport
from core.operational_runtime import OperationalRuntime
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from core.p128_learning_professor import LearningProfessor, ProfessorActivitySpec
from core.p128_learning_source_gate import LearningSource, LearningSourceGate, LearningSourceStatus, LearningSourceType
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine
from core.senior_context_orchestrator import SeniorContextInput, SeniorContextOrchestrator
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle
from integration.news_provider import UnconfiguredNewsProvider
from security.identity_boundary import IdentityPolicy
from security.production_operation_gate import ProductionOperationGate
from security.request_context import ProductionRequestContext, require_production_context
from storage.production_boundary import ProductionStoragePolicy


class EcosystemService:
    """Application orchestration; broker execution remains outside this layer."""

    def __init__(self, engine: SignalEngine | None = None, decision_store: DecisionStore | None = None, production_storage: ProductionStoragePolicy | None = None, operational_runtime: OperationalRuntime | None = None) -> None:
        self.engine = engine or SignalEngine()
        self.store = decision_store or DecisionStore()
        self.memory: list[DecisionRecord] = self.store.load()
        self.risk = RiskManager()
        self.news = UnconfiguredNewsProvider()
        self.identity = IdentityPolicy()
        self.production_storage = production_storage or ProductionStoragePolicy()
        self.production_gate = ProductionOperationGate(self.production_storage)
        self.operational_runtime = operational_runtime
        self.learning_source_gate = LearningSourceGate()
        self.learning_professor = LearningProfessor()
        self.learning_sources: dict[str, LearningSource] = {}
        self.learning_resources: dict[str, LearningResource] = {}
        self.learning_observations: list[LearningObservation] = []
        self.learning_activities: dict[str, LearningActivity] = {}
        self.learning_attempts: list[LearningAttempt] = []
        self.senior_context = SeniorContextOrchestrator()

    def require_production_context(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return require_production_context(subject_id=subject_id, tenant_id=tenant_id)

    def authorize_production_operation(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return self.production_gate.authorize(subject_id=subject_id, tenant_id=tenant_id)

    def _owner_context(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext | None:
        if subject_id is None and tenant_id is None:
            return None
        return self.require_production_context(subject_id=subject_id, tenant_id=tenant_id)

    def _scoped_memory(self, owner: ProductionRequestContext | None) -> list[DecisionRecord]:
        if owner is None:
            return list(self.memory)
        return [record for record in self.memory if record.owned_by(subject_id=owner.subject_id, tenant_id=owner.tenant_id)]

    def update_market_data_snapshot(self, snapshot: BrokerMarketDataSnapshot, *, now: datetime, expected_interval_seconds: int | None = None) -> MarketDataRuntimeReport:
        if self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        return self.operational_runtime.market_data.update(snapshot, now=now, expected_interval_seconds=expected_interval_seconds)

    def analyze(self, payload: dict[str, Any], *, persist: bool = True, subject_id: str | None = None, tenant_id: str | None = None) -> DecisionRecord:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        result = self.engine.evaluate(score=payload.get("score", 50), confirmed=payload.get("confirmed", False), filters_ok=payload.get("filters_ok", True), symbol=payload.get("symbol"), timeframe=payload.get("timeframe"))
        record = DecisionRecord.from_analysis(result)
        if owner is not None:
            record = record.with_owner(subject_id=owner.subject_id, tenant_id=owner.tenant_id)
        if persist:
            self._persist_records([record])
        return record

    def _persist_records(self, records: list[DecisionRecord]) -> None:
        if not records:
            return
        self.store.save_many(records)
        self.memory.extend(records)

    def assess_senior_context(self, *, context_id: str, candles: Iterable[Candle], available_nodes: Iterable[str], observed_nodes: Iterable[str], gaps: dict[str, str] | None = None, relationships_reviewed: Iterable[str] = (), risk_observations: Iterable[RiskObservation] = (), validated_knowledge_ids: Iterable[str] = (), available_risk_domains: Iterable[RiskDomain] = tuple(RiskDomain)) -> Any:
        request = SeniorContextInput(context_id=context_id, candles=tuple(candles), available_nodes=tuple(available_nodes), observed_nodes=tuple(observed_nodes), gaps=dict(gaps or {}), relationships_reviewed=tuple(relationships_reviewed), risk_observations=tuple(risk_observations), validated_knowledge_ids=tuple(validated_knowledge_ids), available_risk_domains=tuple(available_risk_domains))
        return self.senior_context.assess(request)

    def replay(self, cases: Iterable[dict[str, Any]], *, subject_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        from core.replay_policy import prevalidate_replay_cases
        accepted_cases = prevalidate_replay_cases(cases)
        records: list[DecisionRecord] = []
        for payload in accepted_cases:
            records.append(self.analyze(payload, persist=False, subject_id=owner.subject_id if owner else None, tenant_id=owner.tenant_id if owner else None))
        self._persist_records(records)
        return [{"step": index, **record.to_dict()} for index, record in enumerate(records, start=1)]

    def record_outcome(self, decision_id: str, outcome: str, *, subject_id: str | None = None, tenant_id: str | None = None) -> DecisionRecord:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        for index, record in enumerate(self.memory):
            if record.decision_id == decision_id:
                if owner is None:
                    if record.subject_id is not None or record.tenant_id is not None:
                        raise PermissionError("trusted scope is required for owned decision")
                elif not record.owned_by(subject_id=owner.subject_id, tenant_id=owner.tenant_id):
                    raise PermissionError("decision ownership does not match trusted scope")
                updated = record.with_outcome(outcome)
                self.store.save(updated)
                self.memory[index] = updated
                return updated
        raise ValueError("decision_id não encontrado")

    def statistics(self, *, subject_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        scoped = self._scoped_memory(owner)
        breakdowns = summarize_breakdowns(scoped)
        return {**asdict(summarize(scoped)), "periods": summarize_periods(scoped), "breakdowns": {**breakdowns, "by_symbol": breakdowns["symbols"], "by_timeframe": breakdowns["timeframes"], "by_signal": breakdowns["signals"], "by_score_band": breakdowns["score_bands"]}}

    def memory_view(self, limit: int = 50, *, subject_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        return [item.to_dict() for item in self._scoped_memory(owner)[-limit:]][::-1]

    def screen_learning_source(self, payload: dict[str, Any]) -> LearningSource:
        source_type = LearningSourceType(str(payload.get("source_type", "LINK")).upper())
        source = self.learning_source_gate.intake(source_id=str(payload.get("source_id", "")), source_type=source_type, uri=str(payload.get("uri", "")))
        if source.source_id in self.learning_sources:
            raise ValueError("source_id já cadastrado")
        self.learning_sources[source.source_id] = source
        return source

    def validate_learning_source(self, source: LearningSource, *, content_verified: bool, security_checked: bool) -> LearningSource:
        updated = self.learning_source_gate.validate_content(source, content_verified=content_verified, security_checked=security_checked)
        self.learning_sources[updated.source_id] = updated
        return updated

    def admit_learning_knowledge(self, source: LearningSource, *, knowledge_validated: bool) -> LearningSource:
        updated = self.learning_source_gate.admit_knowledge(source, knowledge_validated=knowledge_validated)
        self.learning_sources[updated.source_id] = updated
        return updated

    def learning_sources_view(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"source_type": item.source_type.value, "status": item.status.value} for item in self.learning_sources.values()]

    def add_learning_resource(self, payload: dict[str, Any]) -> LearningResource:
        resource = LearningResource(resource_id=str(payload.get("resource_id", "")), title=str(payload.get("title", "")), content_type=ContentType(str(payload.get("content_type", "OTHER")).upper()), source_url=payload.get("source_url"), source_name=payload.get("source_name"), status=LearningStatus(str(payload.get("status", "RECEIVED")).upper()), tags=normalize_tags(tuple(payload.get("tags", ()) or ())))
        if resource.resource_id in self.learning_resources:
            raise ValueError("resource_id já cadastrado")
        if resource.source_url:
            source_type = {ContentType.VIDEO: LearningSourceType.VIDEO, ContentType.DOCUMENT: LearningSourceType.DOCUMENT}.get(resource.content_type, LearningSourceType.LINK)
            self.screen_learning_source({"source_id": resource.resource_id, "source_type": source_type.value, "uri": resource.source_url})
        self.learning_resources[resource.resource_id] = resource
        return resource

    def learning_resources_view(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"content_type": item.content_type.value, "status": item.status.value, "source_security": (self.learning_sources[item.resource_id].status.value if item.resource_id in self.learning_sources else None)} for item in self.learning_resources.values()]

    def add_learning_observation(self, payload: dict[str, Any]) -> LearningObservation:
        resource_id = str(payload.get("resource_id", ""))
        validated = bool(payload.get("validated", False))
        if resource_id not in self.learning_resources:
            raise ValueError("resource_id não encontrado")
        source = self.learning_sources.get(resource_id)
        if validated and source is not None and (source.status is not LearningSourceStatus.VALIDATED or not source.knowledge_validated):
            raise ValueError("external learning knowledge must pass source and knowledge validation first")
        observation = LearningObservation(resource_id=resource_id, statement=str(payload.get("statement", "")), concepts=normalize_tags(tuple(payload.get("concepts", ()) or ())), evidence=payload.get("evidence"), confidence=payload.get("confidence"), validated=validated)
        self.learning_observations.append(observation)
        return observation

    def learning_observations_view(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.learning_observations]

    def add_learning_activity(self, payload: dict[str, Any]) -> LearningActivity:
        activity = LearningActivity(activity_id=str(payload.get("activity_id", "")), prompt=str(payload.get("prompt", "")), expected_concepts=normalize_tags(tuple(payload.get("expected_concepts", ()) or ())), difficulty=str(payload.get("difficulty", "UNSPECIFIED")))
        if activity.activity_id in self.learning_activities:
            raise ValueError("activity_id já cadastrado")
        self.learning_activities[activity.activity_id] = activity
        return activity

    def generate_professor_activity(self, payload: dict[str, Any]) -> LearningActivity:
        activity = self.learning_professor.build_activity(ProfessorActivitySpec(activity_id=str(payload.get("activity_id", "")), knowledge_id=str(payload.get("knowledge_id", "")), statement=str(payload.get("statement", "")), concept=str(payload.get("concept", "")), difficulty=str(payload.get("difficulty", "INTERMEDIATE"))), knowledge_validated=bool(payload.get("knowledge_validated", False)))
        if activity.activity_id in self.learning_activities:
            raise ValueError("activity_id já cadastrado")
        self.learning_activities[activity.activity_id] = activity
        return activity

    def learning_activities_view(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.learning_activities.values()]

    def add_learning_attempt(self, payload: dict[str, Any]) -> LearningAttempt:
        activity_id = str(payload.get("activity_id", ""))
        if activity_id not in self.learning_activities:
            raise ValueError("activity_id não encontrado")
        attempt = LearningAttempt(activity_id=activity_id, answer=str(payload.get("answer", "")), correct=payload.get("correct"), feedback=str(payload.get("feedback", "")))
        self.learning_attempts.append(attempt)
        return attempt

    def learning_summary(self) -> dict[str, Any]:
        return {"resources": self.learning_resources_view(), "observations": self.learning_observations_view(), "activities": self.learning_activities_view(), "attempts": [asdict(item) for item in self.learning_attempts], "learning_sources": self.learning_sources_view(), "execution_allowed": False, "learning_authorizes_trading": False, "external_learning_sources_require_validation": True, "professor_uses_validated_knowledge_only": True}

    def risk_status(self) -> dict[str, Any]:
        decision = self.risk.evaluate()
        return {"allowed": decision.allowed, "reason": decision.reason, "configured_limits": {"daily_loss_limit": self.risk.daily_loss_limit, "max_operations": self.risk.max_operations, "max_consecutive_losses": self.risk.max_consecutive_losses}, "news_provider": "UNCONFIGURED"}

    def news_status(self, limit: int = 10) -> dict[str, Any]:
        return {"provider": "UNCONFIGURED", "live": False, "items": [asdict(item) for item in self.news.latest(limit=limit)]}

    def connections(self) -> dict[str, Any]:
        return {"decision_core": "ONLINE", "execution_gateway": "ONLINE", "ic_markets_mt5_demo": "DEMO_VALIDADO", "cTrader": "FUTURO_NAO_BLOQUEANTE", "saas": self.saas_status()["runtime"], "real": "DESABILITADO"}

    def saas_status(self) -> dict[str, Any]:
        identity_status = self.identity.status()
        production_storage_status = self.production_storage.status()
        return {"runtime": "FOUNDATION", "provider_neutral": True, "paid_dependency_required": False, "tenant_scoped_access": "BOUNDARY_READY", "identity": identity_status, "production_storage": production_storage_status, "authentication_provider": "NOT_CONFIGURED", "billing": "OUTSIDE_CORE", "dashboard_onboarding": "NOT_CONFIGURED", "real_execution": "DISABLED"}

    def operational_observability(self) -> dict[str, Any]:
        runtime = self.operational_runtime
        if runtime is None:
            return {"execution": {"allowed": False, "mode": "DEMO", "state": "NOT_CONNECTED", "real": "DISABLED"}, "reconciliation": {"state": "NOT_CONNECTED", "pending_request_ids": [], "unknown_request_ids": []}, "recovery": {"state": "NOT_CONNECTED", "can_resume": False, "message": "runtime operacional não conectado ao serviço"}, "kill_switch": {"state": "NOT_CONNECTED", "enabled": False, "reason": None}, "market_data": {"health": "NOT_CONNECTED", "safe_for_analysis": False, "source": None, "symbol": None, "timeframe": None, "candle_count": None, "stale": None, "message": "fonte de candles ainda não conectada ao runtime"}}
        health = runtime.health.assess()
        recovery = runtime.recovery.assess()
        kill = runtime.kill_switch.state
        market_data = runtime.market_data.status()
        market_health = str(market_data.get("health"))
        market_blocked = market_health in {"INVALID", "STALE", "GAP", "NOT_CONNECTED"}
        blocked = (not recovery.can_resume) or kill.enabled or health.state.value == "BLOCKED" or market_blocked
        return {"execution": {"allowed": False, "mode": "DEMO", "state": "BLOCKED" if blocked else "READY_DEMO", "real": "DISABLED"}, "reconciliation": {"state": "REQUIRED" if recovery.state.value == "REQUIRES_RECONCILIATION" else "NOT_REQUIRED", "pending_request_ids": list(recovery.pending_request_ids), "unknown_request_ids": list(recovery.unknown_request_ids)}, "recovery": {"state": recovery.state.value, "can_resume": recovery.can_resume, "message": recovery.message}, "kill_switch": {"state": "ACTIVE" if kill.enabled else "CLEAR", "enabled": kill.enabled, "reason": kill.reason}, "runtime_health": {"state": health.state.value, "ledger_entries": health.ledger_entries, "pending_executions": health.pending_executions, "unknown_executions": health.unknown_executions, "recovery_state": health.recovery_state.value, "message": health.message}, "market_data": market_data}

    def system_status(self) -> dict[str, Any]:
        production_storage = self.production_storage.status()
        production_gate = self.production_gate.status()
        identity = self.identity.status()
        components = {"decision_engine": "ONLINE", "memory": "ONLINE", "replay": "ONLINE", "statistics": "ONLINE", "risk_gate": "ONLINE", "learning": "ONLINE", "psychology": "ONLINE" if getattr(self, "preferences", None) is None or self.preferences.preferences.psychology_enabled else "DISABLED", "news": "AGUARDANDO_FONTE", "mt5_demo": "DEMO_VALIDADO", "real": "DESABILITADO", "saas": "FOUNDATION", "production_storage": str(production_storage.get("status", production_storage.get("state", "UNKNOWN"))), "production_operation_gate": str(production_gate.get("storage_state", production_gate.get("state", "UNKNOWN"))), "trusted_identity_provider": str(identity["trusted_identity_provider"]), "tenant_isolation": str(identity["tenant_isolation"])}
        maintenance = self.maintenance.status() if hasattr(self, "maintenance") else {"status": "NOT_CONFIGURED"}
        alerts = build_health_alerts(components)
        if maintenance.get("status") == MaintenanceStatus.ACTIVE.value:
            alerts = tuple(alerts) + tuple()
        health = "CRITICAL" if any(alert.severity == "CRITICAL" for alert in alerts) else ("WARNING" if alerts else "OK")
        return {"mode": "SIMULACAO", "execution_allowed": False, "execution": "bloqueada_por_padrao", "decision_engine": components["decision_engine"], "memory": components["memory"], "replay": components["replay"], "statistics": components["statistics"], "risk_gate": components["risk_gate"], "learning": components["learning"], "psychology": components["psychology"], "news": components["news"], "mt5_demo": components["mt5_demo"], "real": components["real"], "saas": components["saas"], "components": components, "maintenance": maintenance, "health": health, "alerts": [alert.to_dict() for alert in alerts], "memory_persistence": "SQLITE" if self.store.database_path else "IN_MEMORY", "production_storage": production_storage, "production_operation_gate": production_gate, "operational_observability": self.operational_observability(), **identity}

    def health_alerts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in build_health_alerts(self.operational_observability())]
