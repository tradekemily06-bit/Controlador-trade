from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore
from analysis.decision_report import build_decision_report, export_decision_report
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from core.ecosystem_health import build_health_alerts
from core.operational_alerts import build_operational_incidents
from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.ecosystem_state_store import EcosystemStateStore
from core.notification_outbox import PersistentNotificationOutbox
from core.learning_content import ContentType, LearningActivity, LearningAttempt, LearningObservation, LearningResource, LearningStatus, normalize_tags
from core.learning_state_store import LearningStateStore
from core.market_data_runtime_integrity import MarketDataRuntimeReport
from core.operational_runtime import OperationalRuntime
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from core.p128_learning_professor import LearningProfessor, ProfessorActivitySpec
from core.p128_learning_source_gate import LearningSource, LearningSourceGate, LearningSourceStatus, LearningSourceType
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine
from core.senior_context_orchestrator import SeniorContextInput, SeniorContextOrchestrator
from integration.controlled_automation_service import ControlledAutomationService
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle
from integration.rss_news_provider import NewsProvider, RSSNewsProvider, UnconfiguredNewsProvider
from analysis.news_event_intelligence import classify_news_batch
from analysis.news_evidence_corroboration import NewsEvidenceCorroborator
from security.identity_boundary import IdentityPolicy
from security.production_operation_gate import ProductionOperationGate
from security.request_context import ProductionRequestContext, require_production_context
from storage.production_boundary import ProductionStoragePolicy


class EcosystemService:
    """Application orchestration; broker execution remains outside this layer."""

    def __init__(self, engine: SignalEngine | None = None, decision_store: DecisionStore | None = None, production_storage: ProductionStoragePolicy | None = None, operational_runtime: OperationalRuntime | None = None, learning_state_store: LearningStateStore | None = None, notification_state_store: EcosystemStateStore | None = None, notification_center: EcosystemNotificationCenter | None = None, notification_outbox: PersistentNotificationOutbox | None = None, news_provider: NewsProvider | None = None, news_evidence_correlator: NewsEvidenceCorroborator | None = None) -> None:
        self.engine = engine or SignalEngine()
        self.store = decision_store or DecisionStore()
        self.memory: list[DecisionRecord] = self.store.load()
        self.risk = RiskManager()
        self.news = news_provider if news_provider is not None else RSSNewsProvider.from_environment()
        self.news_evidence_correlator = news_evidence_correlator
        self.news_polling_worker = None
        self.news_polling_managed = False
        self.identity = IdentityPolicy()
        self.production_storage = production_storage or ProductionStoragePolicy()
        self.production_gate = ProductionOperationGate(self.production_storage)
        self.operational_runtime = operational_runtime
        self.learning_source_gate = LearningSourceGate()
        self.learning_professor = LearningProfessor()
        self.learning_state_store = learning_state_store
        learning_state = learning_state_store.load() if learning_state_store is not None else {}
        self.learning_sources: dict[str, LearningSource] = learning_state.get('sources', {})
        self.learning_resources: dict[str, LearningResource] = learning_state.get('resources', {})
        self.learning_observations: list[LearningObservation] = learning_state.get('observations', [])
        self.learning_activities: dict[str, LearningActivity] = learning_state.get('activities', {})
        self.learning_attempts: list[LearningAttempt] = learning_state.get('attempts', [])
        self.notification_state_store = notification_state_store
        self.notification_outbox = notification_outbox
        self.notifications = notification_center or EcosystemNotificationCenter()
        if self.notification_state_store is not None:
            self.notifications.restore(self.notification_state_store.load_notifications())
        self.senior_context = SeniorContextOrchestrator()
        self.automation = ControlledAutomationService(
            lifecycle_store=(operational_runtime.automation_lifecycle if operational_runtime is not None else None)
        )

    def _notification_visible(self, item: EcosystemNotification) -> bool:
        return isinstance(item, EcosystemNotification)

    def _persist_notifications(self) -> None:
        if self.notification_state_store is not None:
            self.notification_state_store.save_notifications([
                asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
                for item in self.notifications.all()
            ])

    def publish_notification(self, notification: EcosystemNotification) -> EcosystemNotification:
        published = self.notifications.publish(notification)
        self._persist_notifications()
        if self.notification_outbox is not None:
            self.notification_outbox.enqueue(
                published.notification_id,
                {
                    "notification_id": published.notification_id,
                    "kind": published.kind.value,
                    "severity": published.severity.value,
                    "title": published.title,
                    "message": published.message,
                    "requires_attention": published.requires_attention,
                    "blocking": published.blocking,
                },
            )
        return published

    def notification_summary(self) -> dict[str, Any]:
        counts = self.notifications.summarize(self.notifications.all())
        return {
            "total": len(self.notifications.all()),
            "by_severity": counts,
            "persistence": "SQLITE" if self.notification_state_store is not None else "IN_MEMORY",
            "external_delivery": "OUTBOX_ONLY_NO_PROVIDER" if self.notification_outbox is not None else "NOT_CONFIGURED",
            "outbox": self.notification_outbox.status_counts() if self.notification_outbox is not None else None,
        }

    def _persist_learning_state(self) -> None:
        if self.learning_state_store is not None:
            self.learning_state_store.save(
                sources=self.learning_sources,
                resources=self.learning_resources,
                observations=self.learning_observations,
                activities=self.learning_activities,
                attempts=self.learning_attempts,
            )

    def require_production_context(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return require_production_context(subject_id=subject_id, tenant_id=tenant_id)

    def authorize_production_operation(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return self.production_gate.authorize(subject_id=subject_id, tenant_id=tenant_id)

    def update_market_data_snapshot(self, snapshot: BrokerMarketDataSnapshot, *, now: datetime, expected_interval_seconds: int | None = None) -> MarketDataRuntimeReport:
        if self.operational_runtime is None:
            raise RuntimeError("runtime operacional não conectado")
        return self.operational_runtime.market_data.update(snapshot, now=now, expected_interval_seconds=expected_interval_seconds)

    def analyze(self, payload: dict[str, Any]) -> DecisionRecord:
        result = self.engine.evaluate(score=payload.get("score", 50), confirmed=payload.get("confirmed", False), filters_ok=payload.get("filters_ok", True), symbol=payload.get("symbol"), timeframe=payload.get("timeframe"))
        record = DecisionRecord.from_analysis(result)
        self.memory.append(record)
        self.store.save(record)
        return record

    def assess_senior_context(
        self,
        *,
        context_id: str,
        candles: Iterable[Candle],
        available_nodes: Iterable[str],
        observed_nodes: Iterable[str],
        gaps: dict[str, str] | None = None,
        relationships_reviewed: Iterable[str] = (),
        risk_observations: Iterable[RiskObservation] = (),
        validated_knowledge_ids: Iterable[str] = (),
        available_risk_domains: Iterable[RiskDomain] = tuple(RiskDomain),
    ) -> Any:
        """Run the senior contextual layer without creating an operation.

        This is deliberately separate from ``analyze`` until the contextual
        output has its own decision-gate integration and regression coverage.
        It never converts a score, candle or contextual assessment directly
        into execution authority.
        """
        request = SeniorContextInput(
            context_id=context_id,
            candles=tuple(candles),
            available_nodes=tuple(available_nodes),
            observed_nodes=tuple(observed_nodes),
            gaps=dict(gaps or {}),
            relationships_reviewed=tuple(relationships_reviewed),
            risk_observations=tuple(risk_observations),
            validated_knowledge_ids=tuple(validated_knowledge_ids),
            available_risk_domains=tuple(available_risk_domains),
        )
        return self.senior_context.assess(request)

    def replay(self, cases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, payload in enumerate(cases, start=1):
            if not isinstance(payload, dict):
                raise ValueError("cada cenário deve ser um objeto")
            record = self.analyze(payload)
            results.append({"step": index, **record.to_dict()})
        return results

    def record_outcome(self, decision_id: str, outcome: str) -> DecisionRecord:
        for index, record in enumerate(self.memory):
            if record.decision_id == decision_id:
                updated = record.with_outcome(outcome, source="MANUAL_STUDY")
                self.memory[index] = updated
                self.store.save(updated)
                return updated
        raise ValueError("decision_id não encontrado")

    def statistics(self) -> dict[str, Any]:
        breakdowns = summarize_breakdowns(self.memory)
        return {**asdict(summarize(self.memory)), "periods": summarize_periods(self.memory), "breakdowns": {**breakdowns, "by_symbol": breakdowns["symbols"], "by_timeframe": breakdowns["timeframes"], "by_signal": breakdowns["signals"], "by_score_band": breakdowns["score_bands"]}}

    def decision_report(self, *, limit: int = 1000) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit deve ser um inteiro de 1 a 1000")
        records = self.memory[-limit:]
        report = build_decision_report(records, self.statistics())
        return {**report, "export_json": export_decision_report(report)}

    def memory_view(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        return [item.to_dict() for item in self.memory[-limit:]][::-1]

    def screen_learning_source(self, payload: dict[str, Any]) -> LearningSource:
        source_type = LearningSourceType(str(payload.get("source_type", "LINK")).upper())
        source = self.learning_source_gate.intake(source_id=str(payload.get("source_id", "")), source_type=source_type, uri=str(payload.get("uri", "")))
        if source.source_id in self.learning_sources:
            raise ValueError("source_id já cadastrado")
        self.learning_sources[source.source_id] = source
        self._persist_learning_state()
        return source

    def validate_learning_source(self, source: LearningSource, *, content_verified: bool, security_checked: bool) -> LearningSource:
        updated = self.learning_source_gate.validate_content(source, content_verified=content_verified, security_checked=security_checked)
        self.learning_sources[updated.source_id] = updated
        self._persist_learning_state()
        return updated

    def admit_learning_knowledge(self, source: LearningSource, *, knowledge_validated: bool) -> LearningSource:
        updated = self.learning_source_gate.admit_knowledge(source, knowledge_validated=knowledge_validated)
        self.learning_sources[updated.source_id] = updated
        self._persist_learning_state()
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
        self._persist_learning_state()
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
        self._persist_learning_state()
        return observation

    def learning_observations_view(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.learning_observations]

    def add_learning_activity(self, payload: dict[str, Any]) -> LearningActivity:
        activity = LearningActivity(activity_id=str(payload.get("activity_id", "")), prompt=str(payload.get("prompt", "")), expected_concepts=normalize_tags(tuple(payload.get("expected_concepts", ()) or ())), difficulty=str(payload.get("difficulty", "UNSPECIFIED")))
        if activity.activity_id in self.learning_activities:
            raise ValueError("activity_id já cadastrado")
        self.learning_activities[activity.activity_id] = activity
        self._persist_learning_state()
        return activity

    def generate_professor_activity(self, payload: dict[str, Any]) -> LearningActivity:
        activity = self.learning_professor.build_activity(ProfessorActivitySpec(activity_id=str(payload.get("activity_id", "")), knowledge_id=str(payload.get("knowledge_id", "")), statement=str(payload.get("statement", "")), concept=str(payload.get("concept", "")), difficulty=str(payload.get("difficulty", "INTERMEDIATE"))), knowledge_validated=bool(payload.get("knowledge_validated", False)))
        if activity.activity_id in self.learning_activities:
            raise ValueError("activity_id já cadastrado")
        self.learning_activities[activity.activity_id] = activity
        self._persist_learning_state()
        return activity

    def learning_activities_view(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.learning_activities.values()]

    def add_learning_attempt(self, payload: dict[str, Any]) -> LearningAttempt:
        activity_id = str(payload.get("activity_id", ""))
        if activity_id not in self.learning_activities:
            raise ValueError("activity_id não encontrado")
        attempt = LearningAttempt(activity_id=activity_id, answer=str(payload.get("answer", "")), correct=payload.get("correct"), feedback=str(payload.get("feedback", "")))
        self.learning_attempts.append(attempt)
        self._persist_learning_state()
        return attempt

    def learning_summary(self) -> dict[str, Any]:
        return {"resources": self.learning_resources_view(), "observations": self.learning_observations_view(), "activities": self.learning_activities_view(), "attempts": [asdict(item) for item in self.learning_attempts], "learning_sources": self.learning_sources_view(), "execution_allowed": False, "learning_authorizes_trading": False, "external_learning_sources_require_validation": True, "professor_uses_validated_knowledge_only": True}

    def risk_status(self) -> dict[str, Any]:
        decision = self.risk.evaluate()
        news_status = getattr(self.news, "status", None)
        news = news_status() if callable(news_status) else {"configured": False}
        return {"allowed": decision.allowed, "reason": decision.reason, "configured_limits": {"daily_loss_limit": self.risk.daily_loss_limit, "max_operations": self.risk.max_operations, "max_consecutive_losses": self.risk.max_consecutive_losses}, "news_provider": "RSS_ATOM" if news.get("configured") else "UNCONFIGURED"}

    @staticmethod
    def _news_symbol_matches(
        symbol: str | None, assets: Iterable[str], title: str | None = None
    ) -> bool:
        if not symbol:
            return True
        query = symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "")
        if not query:
            return True
        normalized_title = (
            title.upper().replace("/", "").replace("-", "").replace("_", "")
            if isinstance(title, str) else ""
        )
        if query in normalized_title:
            return True
        aliases = {"XAU": "GOLD", "XAG": "SILVER"}
        requested = {aliases.get(query, query)}
        if len(query) == 6 and query.isalpha():
            requested.update(aliases.get(query[index:index + 3], query[index:index + 3]) for index in (0, 3))
        normalized_assets = {str(asset).upper() for asset in assets}
        return bool(requested.intersection(normalized_assets))

    def news_status(self, limit: int = 10, symbol: str | None = None) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50")

        polling_worker = self.news_polling_worker
        polling_status = (
            polling_worker.status()
            if polling_worker is not None and callable(getattr(polling_worker, "status", None))
            else None
        )
        if polling_worker is not None and callable(getattr(polling_worker, "latest_items", None)):
            raw_items = list(polling_worker.latest_items())
            raw_items = [
                item for item in raw_items
                if self._news_symbol_matches(
                    symbol,
                    classify_news_batch([item])[0].get("affected_assets", []),
                    getattr(item, "title", None),
                )
            ]
        elif self.news_polling_managed:
            # The standalone runtime owns collection. If its worker is not
            # configured, reads must not silently become ad-hoc network polls.
            raw_items = []
        else:
            # Compatibility for direct service integrations outside the
            # managed standalone runtime.
            raw_items = self.news.latest(symbol=symbol, limit=limit)

        raw_items = raw_items[:limit]
        items = [asdict(item) for item in raw_items]
        status_method = getattr(self.news, "status", None)
        provider_status = status_method() if callable(status_method) else {
            "configured": not isinstance(self.news, UnconfiguredNewsProvider),
            "live": False,
        }
        configured = bool(provider_status.get("configured", False))

        evidence_errors = 0
        if (
            polling_worker is None
            and not self.news_polling_managed
            and self.news_evidence_correlator is not None
        ):
            # Direct, non-managed service use remains compatible, but source
            # identity still must resolve through the explicit trusted policy.
            ingested_at = datetime.now(timezone.utc)
            source_resolver = getattr(
                self.news_evidence_correlator, "source_id_for_url", None
            )
            for item in raw_items:
                try:
                    article_url = getattr(item, "url", None)
                    if not isinstance(article_url, str) or not callable(source_resolver):
                        raise ValueError("trusted news source resolver is required")
                    source_id = source_resolver(article_url)
                    self.news_evidence_correlator.ingest(
                        item, source_id=source_id, ingested_at=ingested_at
                    )
                except Exception:
                    evidence_errors += 1

        persisted_records = []
        if self.news_evidence_correlator is not None:
            records_method = getattr(self.news_evidence_correlator, "records", None)
            if callable(records_method):
                for record in records_method():
                    payload = record.to_dict() if callable(getattr(record, "to_dict", None)) else record
                    if not isinstance(payload, dict):
                        continue
                    if self._news_symbol_matches(
                        symbol, payload.get("affected_assets", ()), payload.get("title")
                    ):
                        persisted_records.append(payload)

        collection_state = "DIRECT_PROVIDER_READ" if polling_status is None else polling_status.get("last_state", "NOT_RUN")
        collection_live = bool(provider_status.get("live", False))
        if polling_status is not None:
            collection_live = (
                collection_state == "POLL_SUCCEEDED"
                and polling_status.get("last_success_at") is not None
            )
        if (
            evidence_errors > 0
            or collection_state == "PARTIAL"
            or (polling_status is not None and polling_status.get("last_errors", 0) > 0)
        ):
            evidence_state = "PARTIAL"
        elif collection_live and self.news_evidence_correlator is not None:
            evidence_state = "CONNECTED"
        elif self.news_evidence_correlator is None:
            evidence_state = "NOT_CONFIGURED"
        else:
            evidence_state = "WAITING_FOR_FIRST_SUCCESS" if collection_state in {"NOT_RUN", "NOT_YET_POLLED"} else "STALE_OR_UNAVAILABLE"

        return {
            "provider": "RSS_ATOM" if configured else "UNCONFIGURED",
            "configured": configured,
            "live": collection_live,
            "status": provider_status,
            "collection": polling_status or {
                "state": collection_state,
                "mode": "DIRECT_PROVIDER_READ",
                "note": "No background news poller is attached to this service instance.",
            },
            "item_count": len(items),
            "items": items,
            "items_freshness": (
                "CURRENT" if collection_live else ("STALE" if items else "NO_DATA")
            ),
            "classified_items": classify_news_batch(raw_items),
            "evidence_processing": {
                "status": evidence_state,
                "processed": len(persisted_records),
                "records": persisted_records,
                "fact_confirmation": "NEVER_AUTOMATIC",
            },
            "classification": "CONSERVATIVE_HEADLINE_RULES",
            "execution_authorized": False,
        }

    @staticmethod
    def _mt5_demo_status_from_observability(observability: dict[str, Any]) -> str:
        """Report MT5 DEMO as validated only after healthy broker candles reach runtime."""
        market_data = observability.get("market_data", {})
        health = str(market_data.get("health") or "NOT_CONNECTED").upper()
        return "DEMO_VALIDADO" if health == "HEALTHY" else health

    def connections(self) -> dict[str, Any]:
        observability = self.operational_observability()
        mt5_status = self._mt5_demo_status_from_observability(observability)
        return {"decision_core": "ONLINE", "execution_gateway": "ONLINE", "ic_markets_mt5_demo": mt5_status, "cTrader": "FUTURO_NAO_BLOQUEANTE", "saas": self.saas_status()["runtime"], "real": "DESABILITADO"}

    def saas_status(self) -> dict[str, Any]:
        identity_status = self.identity.status()
        production_storage_status = self.production_storage.status()
        return {"runtime": "FOUNDATION", "provider_neutral": True, "paid_dependency_required": False, "tenant_scoped_access": "BOUNDARY_READY", "identity": identity_status, "production_storage": production_storage_status, "authentication_provider": "NOT_CONFIGURED", "billing": "OUTSIDE_CORE", "dashboard_onboarding": "NOT_CONFIGURED", "real_execution": "DISABLED"}

    def operational_observability(self) -> dict[str, Any]:
        runtime = self.operational_runtime
        if runtime is None:
            return {"execution": {"allowed": False, "mode": "DEMO", "state": "NOT_CONNECTED", "real": "DISABLED"}, "reconciliation": {"state": "NOT_CONNECTED", "pending_request_ids": [], "unknown_request_ids": []}, "recovery": {"state": "NOT_CONNECTED", "can_resume": False, "message": "runtime operacional não conectado ao serviço"}, "kill_switch": {"state": "NOT_CONNECTED", "enabled": False, "reason": None}, "market_data": {"health": "NOT_CONNECTED", "safe_for_analysis": False, "source": None, "symbol": None, "timeframe": None, "candle_count": None, "gap_count": None, "stale": None, "message": "fonte de candles ainda não conectada ao runtime"}}
        health = runtime.health.assess()
        recovery = runtime.recovery.assess()
        kill = runtime.kill_switch.state
        market_data = runtime.market_data.status()
        market_health = str(market_data.get("health"))
        market_blocked = market_health in {"INVALID", "STALE", "GAP", "NOT_CONNECTED"}
        blocked = (not recovery.can_resume) or kill.enabled or health.state.value == "BLOCKED" or market_blocked

        # Supervisor state is read-only telemetry. It never grants execution
        # authority and is absent until the deployment supervisor has reported.
        import json
        from pathlib import Path
        supervision: dict[str, Any] = {}
        runtime_dir = Path(runtime.checkpoint_store.path).parent
        for component, filename in (("controller", "controlador-supervisor-status.json"), ("mt5", "mt5-supervisor-status.json")):
            status_path = runtime_dir / filename
            try:
                if status_path.is_file():
                    payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
                    if isinstance(payload, dict):
                        supervision[component] = payload
            except (OSError, ValueError, TypeError):
                supervision[component] = {"state": "UNKNOWN", "reason": "status de supervisão inválido"}

        return {"execution": {"allowed": False, "mode": "DEMO", "state": "BLOCKED" if blocked else "READY_DEMO", "real": "DISABLED"}, "reconciliation": {"state": "REQUIRED" if recovery.state.value == "REQUIRES_RECONCILIATION" else "NOT_REQUIRED", "pending_request_ids": list(recovery.pending_request_ids), "unknown_request_ids": list(recovery.unknown_request_ids)}, "recovery": {"state": recovery.state.value, "can_resume": recovery.can_resume, "message": recovery.message}, "kill_switch": {"state": "ACTIVE" if kill.enabled else "CLEAR", "enabled": kill.enabled, "reason": kill.reason}, "runtime_health": {"state": health.state.value, "ledger_entries": health.ledger_entries, "pending_executions": health.pending_executions, "unknown_executions": health.unknown_executions, "recovery_state": health.recovery_state.value, "message": health.message}, "market_data": market_data, "supervision": supervision}

    def system_status(self) -> dict[str, Any]:
        production_storage = self.production_storage.status()
        production_gate = self.production_gate.status()
        identity = self.identity.status()
        observability = self.operational_observability()
        mt5_status = self._mt5_demo_status_from_observability(observability)
        news_status_method = getattr(self.news, "status", None)
        news_provider_status = news_status_method() if callable(news_status_method) else {"configured": False, "live": False}
        news_component = "ONLINE" if news_provider_status.get("live") else ("FONTE_CONFIGURADA_SEM_DADOS" if news_provider_status.get("configured") else "AGUARDANDO_FONTE")
        components = {"decision_engine": "ONLINE", "memory": "ONLINE", "replay": "ONLINE", "statistics": "ONLINE", "risk_gate": "ONLINE", "automation": "ONLINE", "learning": "ONLINE", "learning_persistence": "SQLITE" if self.learning_state_store is not None else "IN_MEMORY", "notification_persistence": "SQLITE" if self.notification_state_store is not None else "IN_MEMORY", "news": news_component, "mt5_demo": mt5_status, "real": "DESABILITADO", "saas": "FOUNDATION", "production_storage": str(production_storage["state"]), "production_operation_gate": str(production_gate["storage_state"]), "trusted_identity_provider": str(identity["trusted_identity_provider"]), "tenant_isolation": str(identity["tenant_isolation"])}
        alerts = build_health_alerts(components)
        health = "CRITICAL" if any(alert.severity == "CRITICAL" for alert in alerts) else ("WARNING" if alerts else "OK")
        return {"mode": "SIMULACAO", "execution_allowed": False, "execution": "bloqueada_por_padrao", "decision_engine": components["decision_engine"], "memory": components["memory"], "replay": components["replay"], "statistics": components["statistics"], "risk_gate": components["risk_gate"], "learning": components["learning"], "news": components["news"], "mt5_demo": components["mt5_demo"], "real": components["real"], "saas": components["saas"], "components": components, "health": health, "alerts": [alert.to_dict() for alert in alerts], "memory_persistence": "SQLITE" if self.store.database_path else "IN_MEMORY", "learning_persistence": "SQLITE" if self.learning_state_store is not None else "IN_MEMORY", "notification_persistence": "SQLITE" if self.notification_state_store is not None else "IN_MEMORY", "production_storage": production_storage, "production_operation_gate": production_gate, "operational_observability": observability, **identity}

    def health_alerts(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in build_health_alerts(self.operational_observability())]

    def _operational_notifications(self) -> list[dict[str, Any]]:
        """Expose current runtime incidents through the notification channel.

        Incidents are derived from read-only observability at request time;
        this does not mutate runtime state or grant execution authority.
        """
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
            items.append(
                {
                    "notification_id": f"operational-{incident.code}",
                    "kind": kind_by_source.get(incident.source, NotificationKind.SYSTEM_UPDATE).value,
                    "severity": severity_by_incident.get(incident.severity.upper(), NotificationSeverity.IMPORTANT).value,
                    "title": incident.code,
                    "message": incident.message,
                    "requires_attention": incident.severity.upper() == "CRITICAL",
                    "blocking": incident.severity.upper() == "CRITICAL",
                }
            )
        return items

    def notification_items(self, *, include_info: bool = False) -> list[dict[str, Any]]:
        """Return persisted notifications plus current operational incidents."""
        persisted = [
            asdict(item) | {"kind": item.kind.value, "severity": item.severity.value}
            for item in self.notifications.visible(include_info=include_info)
            if self._notification_visible(item)
        ]
        return persisted + self._operational_notifications()
