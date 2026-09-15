from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

from core.learning_content import LearningActivity, LearningAttempt, LearningObservation, LearningResource, ContentType, LearningStatus
from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType


@dataclass
class LearningScope:
    """All user-owned learning state for exactly one tenant+subject pair."""

    sources: dict[str, LearningSource] = field(default_factory=dict)
    resources: dict[str, LearningResource] = field(default_factory=dict)
    observations: list[LearningObservation] = field(default_factory=list)
    activities: dict[str, LearningActivity] = field(default_factory=dict)
    attempts: list[LearningAttempt] = field(default_factory=list)


class ScopedLearningState:
    """Separates learning state by trusted tenant+subject and can persist it durably.

    Without a state store this remains a local/test isolation layer. In public SaaS,
    callers must provide a durable state store so learning data cannot silently
    fall back to process memory. The in-process cache is bounded and is only a
    performance layer; durable storage remains the source of truth.
    """

    NAMESPACE = "learning.state.v1"
    DEFAULT_CACHE_SIZE = 256

    def __init__(self, *, state_store=None, require_durable: bool = False, cache_size: int = DEFAULT_CACHE_SIZE) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be greater than zero")
        self._scopes: OrderedDict[tuple[str, str], LearningScope] = OrderedDict()
        self._cache_size = int(cache_size)
        self._state_store = state_store
        self._require_durable = bool(require_durable)

    @staticmethod
    def _scope(tenant_id: str | None, subject_id: str | None) -> tuple[str, str] | None:
        if tenant_id is None and subject_id is None:
            return None
        tenant = str(tenant_id or "").strip()
        subject = str(subject_id or "").strip()
        if not tenant or not subject:
            raise PermissionError("tenant_id and subject_id are required for scoped learning state")
        return tenant, subject

    @staticmethod
    def _encode(scope: LearningScope) -> dict[str, Any]:
        return {
            "sources": {key: asdict(value) | {"source_type": value.source_type.value, "status": value.status.value} for key, value in scope.sources.items()},
            "resources": {key: asdict(value) | {"content_type": value.content_type.value, "status": value.status.value} for key, value in scope.resources.items()},
            "observations": [asdict(value) for value in scope.observations],
            "activities": {key: asdict(value) for key, value in scope.activities.items()},
            "attempts": [asdict(value) for value in scope.attempts],
        }

    @staticmethod
    def _decode(payload: object) -> LearningScope:
        if not isinstance(payload, dict):
            raise RuntimeError("learning state is corrupt")
        try:
            sources = {str(key): LearningSource(source_id=str(value["source_id"]), source_type=LearningSourceType(str(value["source_type"])), uri=str(value["uri"]), status=LearningSourceStatus(str(value["status"])), content_verified=bool(value.get("content_verified", False)), security_checked=bool(value.get("security_checked", False)), knowledge_validated=bool(value.get("knowledge_validated", False)), operation_eligible=bool(value.get("operation_eligible", False))) for key, value in dict(payload.get("sources", {})).items()}
            resources = {str(key): LearningResource(resource_id=str(value["resource_id"]), title=str(value["title"]), content_type=ContentType(str(value["content_type"])), source_url=value.get("source_url"), source_name=value.get("source_name"), status=LearningStatus(str(value.get("status", LearningStatus.RECEIVED.value))), tags=tuple(value.get("tags", ()) or ())) for key, value in dict(payload.get("resources", {})).items()}
            observations = [LearningObservation(resource_id=str(value["resource_id"]), statement=str(value["statement"]), concepts=tuple(value.get("concepts", ()) or ()), evidence=value.get("evidence"), confidence=value.get("confidence"), validated=bool(value.get("validated", False))) for value in list(payload.get("observations", ()) or ())]
            activities = {str(key): LearningActivity(activity_id=str(value["activity_id"]), prompt=str(value["prompt"]), expected_concepts=tuple(value.get("expected_concepts", ()) or ()), difficulty=str(value.get("difficulty", "UNSPECIFIED"))) for key, value in dict(payload.get("activities", {})).items()}
            attempts = [LearningAttempt(activity_id=str(value["activity_id"]), answer=str(value["answer"]), correct=value.get("correct"), feedback=str(value.get("feedback", ""))) for value in list(payload.get("attempts", ()) or ())]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("learning state is corrupt") from exc
        return LearningScope(sources=sources, resources=resources, observations=observations, activities=activities, attempts=attempts)

    def _load(self, scope: tuple[str, str]) -> LearningScope:
        if self._state_store is None:
            if self._require_durable:
                raise RuntimeError("durable learning state provider is required")
            return LearningScope()
        payload = self._state_store.get(tenant_id=scope[0], subject_id=scope[1], namespace=self.NAMESPACE)
        return LearningScope() if payload is None else self._decode(payload)

    def _save(self, scope_key: tuple[str, str], scope: LearningScope) -> None:
        if self._state_store is None:
            if self._require_durable:
                raise RuntimeError("durable learning state provider is required")
            return
        self._state_store.put(tenant_id=scope_key[0], subject_id=scope_key[1], namespace=self.NAMESPACE, payload=self._encode(scope))

    def _cache(self, scope_key: tuple[str, str], scope: LearningScope) -> LearningScope:
        self._scopes[scope_key] = scope
        self._scopes.move_to_end(scope_key)
        while len(self._scopes) > self._cache_size:
            self._scopes.popitem(last=False)
        return scope

    def get(self, *, tenant_id: str | None, subject_id: str | None) -> LearningScope | None:
        scope = self._scope(tenant_id, subject_id)
        if scope is None:
            if self._require_durable:
                raise PermissionError("trusted tenant and subject scope are required for learning state")
            return None
        cached = self._scopes.get(scope)
        if cached is not None:
            self._scopes.move_to_end(scope)
            return cached
        return self._cache(scope, self._load(scope))

    def persist(self, *, tenant_id: str | None, subject_id: str | None) -> None:
        scope = self._scope(tenant_id, subject_id)
        if scope is None:
            if self._require_durable:
                raise PermissionError("trusted tenant and subject scope are required for learning state")
            return
        current = self._scopes.get(scope)
        if current is None:
            current = self._cache(scope, self._load(scope))
        self._save(scope, current)
