from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from core.ecosystem_health import build_health_alerts
from core.learning_content import (
    ContentType,
    LearningActivity,
    LearningAttempt,
    LearningObservation,
    LearningResource,
    LearningStatus,
    normalize_tags,
)
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine
from integration.news_provider import UnconfiguredNewsProvider
from security.identity_boundary import IdentityPolicy
from security.production_operation_gate import ProductionOperationGate
from security.request_context import ProductionRequestContext, require_production_context
from storage.production_boundary import ProductionStoragePolicy


class EcosystemService:
    """Application orchestration; broker execution remains outside this layer."""

    def __init__(
        self,
        engine: SignalEngine | None = None,
        decision_store: DecisionStore | None = None,
        production_storage: ProductionStoragePolicy | None = None,
    ) -> None:
        self.engine = engine or SignalEngine()
        self.store = decision_store or DecisionStore()
        self.memory: list[DecisionRecord] = self.store.load()
        self.risk = RiskManager()
        self.news = UnconfiguredNewsProvider()
        self.identity = IdentityPolicy()
        self.production_storage = production_storage or ProductionStoragePolicy()
        self.production_gate = ProductionOperationGate(self.production_storage)
        self.learning_resources: dict[str, LearningResource] = {}
        self.learning_observations: list[LearningObservation] = []
        self.learning_activities: dict[str, LearningActivity] = {}
        self.learning_attempts: list[LearningAttempt] = []

    def require_production_context(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return require_production_context(subject_id=subject_id, tenant_id=tenant_id)

    def authorize_production_operation(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        return self.production_gate.authorize(subject_id=subject_id, tenant_id=tenant_id)

    def analyze(self, payload: dict[str, Any]) -> DecisionRecord:
        result = self.engine.evaluate(
            score=payload.get("score", 50),
            confirmed=payload.get("confirmed", False),
            filters_ok=payload.get("filters_ok", True),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
        )
        record = DecisionRecord.from_analysis(result)
        self.memory.append(record)
        self.store.save(record)
        return record

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
                updated = record.with_outcome(outcome)
                self.memory[index] = updated
                self.store.save(updated)
                return updated
        raise ValueError("decision_id não encontrado")

    def statistics(self) -> dict[str, Any]:
        breakdowns = summarize_breakdowns(self.memory)
        return {
            **asdict(summarize(self.memory)),
            "periods": summarize_periods(self.memory),
            "breakdowns": {
                **breakdowns,
                "by_symbol": breakdowns["symbols"],
                "by_timeframe": breakdowns["timeframes"],
                "by_signal": breakdowns["signals"],
                "by_score_band": breakdowns["score_bands"],
            },
        }

    def memory_view(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        return [item.to_dict() for item in self.memory[-limit:]][::-1]

    def add_learning_resource(self, payload: dict[str, Any]) -> LearningResource:
        resource = LearningResource(
            resource_id=str(payload.get("resource_id", "")),
            title=str(payload.get("title", "")),
            content_type=ContentType(str(payload.get("content_type", "OTHER")).upper()),
            source_url=payload.get("source_url"),
            source_name=payload.get("source_name"),
            status=LearningStatus(str(payload.get("status", "RECEIVED")).upper()),
            tags=normalize_tags(tuple(payload.get("tags", ()) or ())),
        )
        if resource.resource_id in self.learning_resources:
            raise ValueError("resource_id já cadastrado")
        self.learning_resources[resource.resource_id] = resource
        return resource

    def learning_resources_view(self) -> list[dict[str, Any]]:
        return [asdict(item) | {"content_type": item.content_type.value, "status": item.status.value} for item in self.learning_resources.values()]

    def add_learning_observation(self, payload: dict[str, Any]) -> LearningObservation:
        observation = LearningObservation(
            resource_id=str(payload.get("resource_id", "")),
            statement=str(payload.get("statement", "")),
            concepts=normalize_tags(tuple(payload.get("concepts", ()) or ())),
            evidence=payload.get("evidence"),
            confidence=payload.get("confidence"),
            validated=bool(payload.get("validated", False)),
        )
        if observation.resource_id not in self.learning_resources:
            raise ValueError("resource_id não encontrado")
        self.learning_observations.append(observation)
        return observation

    def learning_observations_view(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.learning_observations]

    def add_learning_activity(self, payload: dict[str, Any]) -> LearningActivity:
        activity = LearningActivity(
            activity_id=str(payload.get("activity_id", "")),
            prompt=str(payload.get("prompt", "")),
            expected_concepts=normalize_tags(tuple(payload.get("expected_concepts", ()) or ())),
            difficulty=str(payload.get("difficulty", "UNSPECIFIED")),
        )
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
        attempt = LearningAttempt(
            activity_id=activity_id,
            answer=str(payload.get("answer", "")),
            correct=payload.get("correct"),
            feedback=str(payload.get("feedback", "")),
        )
        self.learning_attempts.append(attempt)
        return attempt

    def learning_summary(self) -> dict[str, Any]:
        return {
            "resources": self.learning_resources_view(),
            "observations": self.learning_observations_view(),
            "activities": self.learning_activities_view(),
            "attempts": [asdict(item) for item in self.learning_attempts],
            "execution_allowed": False,
            "learning_authorizes_trading": False,
        }

    def risk_status(self) -> dict[str, Any]:
        decision = self.risk.evaluate()
        return {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "configured_limits": {
                "daily_loss_limit": self.risk.daily_loss_limit,
                "max_operations": self.risk.max_operations,
                "max_consecutive_losses": self.risk.max_consecutive_losses,
            },
            "news_provider": "UNCONFIGURED",
        }

    def news_status(self, limit: int = 10) -> dict[str, Any]:
        return {"provider": "UNCONFIGURED", "live": False, "items": [asdict(item) for item in self.news.latest(limit=limit)]}

    def connections(self) -> dict[str, Any]:
        return {
            "decision_core": "ONLINE",
            "execution_gateway": "ONLINE",
            "ic_markets_mt5_demo": "DEMO_VALIDADO",
            "cTrader": "FUTURO_NAO_BLOQUEANTE",
            "saas": self.saas_status()["runtime"],
            "real": "DESABILITADO",
        }

    def saas_status(self) -> dict[str, Any]:
        identity_status = self.identity.status()
        production_storage_status = self.production_storage.status()
        return {
            "runtime": "FOUNDATION",
            "provider_neutral": True,
            "paid_dependency_required": False,
            "tenant_scoped_access": "BOUNDARY_READY",
            "identity": identity_status,
            "production_storage": production_storage_status,
            "authentication_provider": "NOT_CONFIGURED",
            "billing": "OUTSIDE_CORE",
            "dashboard_onboarding": "NOT_CONFIGURED",
            "real_execution": "DISABLED",
        }

    def system_status(self) -> dict[str, Any]:
        production_storage = self.production_storage.status()
        production_gate = self.production_gate.status()
        identity = self.identity.status()
        components = {
            "decision_engine": "ONLINE",
            "memory": "ONLINE",
            "replay": "ONLINE",
            "statistics": "ONLINE",
            "risk_gate": "ONLINE",
            "learning": "ONLINE",
            "news": "AGUARDANDO_FONTE",
            "mt5_demo": "DEMO_VALIDADO",
            "real": "DESABILITADO",
            "saas": "FOUNDATION",
            "production_storage": str(production_storage["state"]),
            "production_operation_gate": str(production_gate["storage_state"]),
            "trusted_identity_provider": str(identity["trusted_identity_provider"]),
            "tenant_isolation": str(identity["tenant_isolation"]),
        }
        alerts = build_health_alerts(components)
        health = "CRITICAL" if any(alert.severity == "CRITICAL" for alert in alerts) else ("WARNING" if alerts else "OK")
        return {
            "mode": "SIMULACAO",
            "execution_allowed": False,
            "execution": "bloqueada_por_padrao",
            "decision_engine": components["decision_engine"],
            "memory": components["memory"],
            "replay": components["replay"],
            "statistics": components["statistics"],
            "risk_gate": components["risk_gate"],
            "learning": components["learning"],
            "news": components["news"],
            "mt5_demo": components["mt5_demo"],
            "real": components["real"],
            "saas": components["saas"],
            "components": components,
            "health": health,
            "alerts": [alert.to_dict() for alert in alerts],
            "memory_persistence": "SQLITE" if self.store.database_path else "IN_MEMORY",
            "production_storage": production_storage,
            "production_operation_gate": production_gate,
            **identity,
        }
