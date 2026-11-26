from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from core.ecosystem_state_store import EcosystemStateStore
from core.learning_content import (
    ContentType, LearningActivity, LearningAttempt, LearningObservation,
    LearningResource, LearningStatus,
)
from core.p128_learning_source_gate import (
    LearningSource, LearningSourceStatus, LearningSourceType,
)


class LearningStateStore:
    """Typed, versioned persistence for the Study area.

    The generic ecosystem SQLite store remains the durable backend; this
    adapter validates and reconstructs domain objects instead of loading
    untrusted JSON directly into application state.
    """

    KEY = "learning_state"
    SCHEMA_VERSION = 1

    def __init__(self, state_store: EcosystemStateStore) -> None:
        self.state_store = state_store

    @staticmethod
    def _enum(value: Any, enum_type):
        return enum_type(value)

    @classmethod
    def _source(cls, value: Mapping[str, Any]) -> LearningSource:
        return LearningSource(
            source_id=str(value["source_id"]),
            source_type=cls._enum(value["source_type"], LearningSourceType),
            uri=str(value["uri"]),
            status=cls._enum(value["status"], LearningSourceStatus),
            content_verified=bool(value.get("content_verified", False)),
            security_checked=bool(value.get("security_checked", False)),
            knowledge_validated=bool(value.get("knowledge_validated", False)),
            operation_eligible=False,
        )

    def load(self) -> dict[str, Any]:
        raw = self.state_store.load(self.KEY)
        if raw is None:
            return {"sources": {}, "resources": {}, "observations": [], "activities": {}, "attempts": []}
        if not isinstance(raw, dict) or raw.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported or invalid learning state schema")
        try:
            sources = {
                str(key): self._source(value)
                for key, value in raw.get("sources", {}).items()
            }
            resources = {
                str(key): LearningResource(
                    resource_id=str(value["resource_id"]),
                    title=str(value["title"]),
                    content_type=self._enum(value["content_type"], ContentType),
                    source_url=value.get("source_url"),
                    source_name=value.get("source_name"),
                    status=self._enum(value.get("status", "RECEIVED"), LearningStatus),
                    tags=tuple(value.get("tags", ())),
                )
                for key, value in raw.get("resources", {}).items()
            }
            observations = [
                LearningObservation(
                    resource_id=str(value["resource_id"]),
                    statement=str(value["statement"]),
                    concepts=tuple(value.get("concepts", ())),
                    evidence=value.get("evidence"),
                    confidence=value.get("confidence"),
                    validated=bool(value.get("validated", False)),
                )
                for value in raw.get("observations", [])
            ]
            activities = {
                str(key): LearningActivity(
                    activity_id=str(value["activity_id"]),
                    prompt=str(value["prompt"]),
                    expected_concepts=tuple(value.get("expected_concepts", ())),
                    difficulty=str(value.get("difficulty", "UNSPECIFIED")),
                )
                for key, value in raw.get("activities", {}).items()
            }
            attempts = [
                LearningAttempt(
                    activity_id=str(value["activity_id"]),
                    answer=str(value["answer"]),
                    correct=value.get("correct"),
                    feedback=str(value.get("feedback", "")),
                )
                for value in raw.get("attempts", [])
            ]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("persisted learning state failed domain validation") from exc
        if any(item.resource_id not in resources for item in observations):
            raise ValueError("learning observation references an unknown resource")
        if any(item.activity_id not in activities for item in attempts):
            raise ValueError("learning attempt references an unknown activity")
        return {
            "sources": sources, "resources": resources,
            "observations": observations, "activities": activities,
            "attempts": attempts,
        }

    def save(self, *, sources, resources, observations, activities, attempts) -> None:
        def encode(items):
            return {
                key: asdict(value)
                for key, value in items.items()
            }
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "sources": encode(sources),
            "resources": encode(resources),
            "observations": [asdict(item) for item in observations],
            "activities": encode(activities),
            "attempts": [asdict(item) for item in attempts],
        }
        self.state_store.save(self.KEY, payload)
