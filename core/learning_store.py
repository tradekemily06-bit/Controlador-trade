from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from core.learning_content import (
    ContentType,
    LearningActivity,
    LearningAttempt,
    LearningObservation,
    LearningResource,
    LearningStatus,
)
from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType


class LearningStore:
    """Optional SQLite persistence for pedagogical memory.

    The store persists only learning/control-plane artifacts. It never stores
    or grants execution authority. When no database is configured, callers keep
    the existing in-memory behavior.
    """

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path if database_path is not None else (
            os.environ.get("CONTROLADOR_LEARNING_DB")
            or os.environ.get("CONTROLADOR_DECISION_DB")
        )
        self._lock = Lock()
        if self.database_path:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path or ":memory:", timeout=5)

    def _initialize(self) -> None:
        try:
            path = Path(self.database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS learning_state "
                    "(state_key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
        except (OSError, sqlite3.Error):
            self.database_path = None

    def save(
        self,
        *,
        learning_sources: dict[str, LearningSource],
        learning_resources: dict[str, LearningResource],
        learning_observations: list[LearningObservation],
        learning_activities: dict[str, LearningActivity],
        learning_attempts: list[LearningAttempt],
    ) -> None:
        if not self.database_path:
            return
        state = {
            "sources": [
                {**asdict(item), "source_type": item.source_type.value, "status": item.status.value}
                for item in learning_sources.values()
            ],
            "resources": [
                {**asdict(item), "content_type": item.content_type.value, "status": item.status.value}
                for item in learning_resources.values()
            ],
            "observations": [asdict(item) for item in learning_observations],
            "activities": [asdict(item) for item in learning_activities.values()],
            "attempts": [asdict(item) for item in learning_attempts],
        }
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO learning_state(state_key, payload) VALUES(?, ?)",
                    ("ecosystem", json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
                )
        except (sqlite3.Error, TypeError, ValueError):
            # Learning persistence must never authorize, retry, or alter trading.
            return

    def load(self) -> tuple[
        dict[str, LearningSource],
        dict[str, LearningResource],
        list[LearningObservation],
        dict[str, LearningActivity],
        list[LearningAttempt],
    ]:
        if not self.database_path:
            return {}, {}, [], {}, []
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT payload FROM learning_state WHERE state_key = ?",
                    ("ecosystem",),
                ).fetchone()
            if not row:
                return {}, {}, [], {}, []
            payload: dict[str, Any] = json.loads(row[0])
            sources = {
                item["source_id"]: LearningSource(
                    source_id=item["source_id"],
                    source_type=LearningSourceType(item["source_type"]),
                    uri=item["uri"],
                    status=LearningSourceStatus(item["status"]),
                    content_verified=bool(item.get("content_verified", False)),
                    security_checked=bool(item.get("security_checked", False)),
                    knowledge_validated=bool(item.get("knowledge_validated", False)),
                    operation_eligible=False,
                )
                for item in payload.get("sources", [])
            }
            resources = {
                item["resource_id"]: LearningResource(
                    resource_id=item["resource_id"],
                    title=item["title"],
                    content_type=ContentType(item["content_type"]),
                    source_url=item.get("source_url"),
                    source_name=item.get("source_name"),
                    status=LearningStatus(item.get("status", LearningStatus.RECEIVED.value)),
                    tags=tuple(item.get("tags", [])),
                )
                for item in payload.get("resources", [])
            }
            observations = [
                LearningObservation(
                    resource_id=item["resource_id"],
                    statement=item["statement"],
                    concepts=tuple(item.get("concepts", [])),
                    evidence=item.get("evidence"),
                    confidence=item.get("confidence"),
                    validated=bool(item.get("validated", False)),
                )
                for item in payload.get("observations", [])
            ]
            activities = {
                item["activity_id"]: LearningActivity(
                    activity_id=item["activity_id"],
                    prompt=item["prompt"],
                    expected_concepts=tuple(item.get("expected_concepts", [])),
                    difficulty=item.get("difficulty", "UNSPECIFIED"),
                )
                for item in payload.get("activities", [])
            }
            attempts = [
                LearningAttempt(
                    activity_id=item["activity_id"],
                    answer=item["answer"],
                    correct=item.get("correct"),
                    feedback=item.get("feedback", ""),
                )
                for item in payload.get("attempts", [])
            ]
            return sources, resources, observations, activities, attempts
        except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return {}, {}, [], {}, []
