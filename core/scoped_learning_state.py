from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

from core.learning_content import LearningActivity, LearningAttempt, LearningObservation, LearningResource, ContentType, LearningStatus
from core.learning_material_review import (
    EffectivenessVerdict,
    LearningMaterialReview,
    MaterialClaimReview,
    MaterialEffectivenessReview,
    MaterialVerdict,
)
from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType


@dataclass
class LearningScope:
    """All user-owned learning state for exactly one tenant+subject pair."""

    sources: dict[str, LearningSource] = field(default_factory=dict)
    resources: dict[str, LearningResource] = field(default_factory=dict)
    observations: list[LearningObservation] = field(default_factory=list)
    activities: dict[str, LearningActivity] = field(default_factory=dict)
    attempts: list[LearningAttempt] = field(default_factory=list)
    material_reviews: dict[str, LearningMaterialReview] = field(default_factory=dict)


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
    def _encode_review(review: LearningMaterialReview) -> dict[str, Any]:
        return {
            "resource_id": review.resource_id,
            "knowledge_level": review.knowledge_level.value,
            "overall_verdict": review.overall_verdict.value,
            "claims": [
                {
                    "claim": item.claim,
                    "verdict": item.verdict.value,
                    "rationale": item.rationale,
                    "matching_reference_ids": list(item.matching_reference_ids),
                    "confidence": item.confidence,
                }
                for item in review.claims
            ],
            "effectiveness": {
                "verdict": review.effectiveness.verdict.value,
                "rationale": review.effectiveness.rationale,
                "sample_size": review.effectiveness.sample_size,
                "tested_period": review.effectiveness.tested_period,
            },
            "limitations": list(review.limitations),
            # This is a safety invariant, not caller-controlled persisted state.
            "operation_authorized": False,
        }

    @staticmethod
    def _decode_review(value: object) -> LearningMaterialReview:
        if not isinstance(value, dict):
            raise RuntimeError("learning material review is corrupt")
        try:
            claims = tuple(
                MaterialClaimReview(
                    claim=str(item["claim"]),
                    verdict=MaterialVerdict(str(item["verdict"])),
                    rationale=str(item["rationale"]),
                    matching_reference_ids=tuple(str(ref) for ref in item.get("matching_reference_ids", ()) or ()),
                    confidence=float(item.get("confidence", 0.0)),
                )
                for item in list(value.get("claims", ()) or ())
            )
            effectiveness_value = dict(value["effectiveness"])
            effectiveness = MaterialEffectivenessReview(
                verdict=EffectivenessVerdict(str(effectiveness_value["verdict"])),
                rationale=str(effectiveness_value["rationale"]),
                sample_size=effectiveness_value.get("sample_size"),
                tested_period=effectiveness_value.get("tested_period"),
            )
            return LearningMaterialReview(
                resource_id=str(value["resource_id"]),
                knowledge_level=MaterialVerdict(str(value["knowledge_level"])),
                overall_verdict=MaterialVerdict(str(value["overall_verdict"])),
                claims=claims,
                effectiveness=effectiveness,
                limitations=tuple(str(item) for item in value.get("limitations", ()) or ()),
                operation_authorized=False,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("learning material review is corrupt") from exc

    @staticmethod
    def _encode(scope: LearningScope) -> dict[str, Any]:
        return {
            "sources": {key: asdict(value) | {"source_type": value.source_type.value, "status": value.status.value} for key, value in scope.sources.items()},
            "resources": {key: asdict(value) | {"content_type": value.content_type.value, "status": value.status.value} for key, value in scope.resources.items()},
            "observations": [asdict(value) for value in scope.observations],
            "activities": {key: asdict(value) for key, value in scope.activities.items()},
            "attempts": [asdict(value) for value in scope.attempts],
            "material_reviews": {key: ScopedLearningState._encode_review(value) for key, value in scope.material_reviews.items()},
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
            material_reviews = {str(key): ScopedLearningState._decode_review(value) for key, value in dict(payload.get("material_reviews", {})).items()}
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("learning state is corrupt") from exc
        return LearningScope(sources=sources, resources=resources, observations=observations, activities=activities, attempts=attempts, material_reviews=material_reviews)

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

    @staticmethod
    def _merge(latest: LearningScope, current: LearningScope) -> LearningScope:
        """Merge additive concurrent learning writes without dropping newer durable data."""
        merged = LearningScope(
            sources=dict(latest.sources),
            resources=dict(latest.resources),
            observations=list(latest.observations),
            activities=dict(latest.activities),
            attempts=list(latest.attempts),
            material_reviews=dict(latest.material_reviews),
        )
        merged.sources.update(current.sources)
        merged.resources.update(current.resources)
        merged.activities.update(current.activities)
        merged.material_reviews.update(current.material_reviews)
        for item in current.observations:
            if item not in merged.observations:
                merged.observations.append(item)
        for item in current.attempts:
            if item not in merged.attempts:
                merged.attempts.append(item)
        return merged

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
        # Durable state is authoritative. Reload on every scoped read so a
        # long-lived worker cannot serve stale learning data after another
        # worker/process updates the same tenant+subject scope. The bounded
        # cache remains useful for non-durable/local mode only.
        if self._state_store is not None:
            return self._cache(scope, self._load(scope))
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
        if self._state_store is not None:
            latest = self._load(scope)
            current = self._merge(latest, current)
        self._cache(scope, current)
        self._save(scope, current)
