"""Durable local economic-calendar ingestion boundary.

Adapters and schedulers are injected by the host. This module normalizes
publisher payloads with trusted source policy and stores append-only
observations; it does not fetch arbitrary URLs or invent missing values.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from analysis.economic_calendar import EconomicCalendarEvent, normalize_calendar_batch


class SQLiteEconomicCalendarStore:
    """Single-host append-only observation store; not a shared multi-replica DB."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:" and Path(self.database_path).is_symlink():
            raise ValueError("economic calendar database path must not be a symlink")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS economic_calendar_observations (
                    source_id TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (source_id, source_event_id, observed_at)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_economic_calendar_scheduled
                ON economic_calendar_observations (scheduled_at, source_id)
                """
            )

    def append_batch(self, events: list[EconomicCalendarEvent] | tuple[EconomicCalendarEvent, ...]) -> int:
        if not isinstance(events, (list, tuple)) or any(
            not isinstance(event, EconomicCalendarEvent) for event in events
        ):
            raise ValueError("events must be a list or tuple of normalized calendar events")
        rows = [
            (
                event.source_id,
                event.source_event_id,
                event.observed_at.isoformat(),
                event.scheduled_at.isoformat(),
                event.status.value,
                event.impact.value,
                json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            for event in events
        ]
        with self._connect() as connection:
            cursor = connection.executemany(
                """
                INSERT OR IGNORE INTO economic_calendar_observations
                (source_id, source_event_id, observed_at, scheduled_at, status, impact, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return max(cursor.rowcount, 0)

    def list_latest(self, *, start_at: str, end_at: str, limit: int = 500) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5000:
            raise ValueError("limit must be between 1 and 5000")
        start = start_at.strip() if isinstance(start_at, str) else ""
        end = end_at.strip() if isinstance(end_at, str) else ""
        if not start or not end or start > end:
            raise ValueError("a valid inclusive time range is required")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM economic_calendar_observations AS current
                WHERE current.scheduled_at >= ? AND current.scheduled_at <= ?
                  AND current.observed_at = (
                    SELECT MAX(previous.observed_at)
                    FROM economic_calendar_observations AS previous
                    WHERE previous.source_id = current.source_id
                      AND previous.source_event_id = current.source_event_id
                  )
                ORDER BY current.scheduled_at ASC, current.source_id ASC
                LIMIT ?
                """,
                (start, end, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


class EconomicCalendarIngestionService:
    """Adapter-facing ingestion service with trusted publisher metadata."""

    def __init__(
        self,
        *,
        store: SQLiteEconomicCalendarStore,
        trusted_sources: Mapping[str, Mapping[str, Any]],
    ) -> None:
        if not isinstance(store, SQLiteEconomicCalendarStore):
            raise ValueError("a calendar store is required")
        if not isinstance(trusted_sources, Mapping) or not trusted_sources:
            raise ValueError("trusted source configuration is required")
        self.store = store
        self.trusted_sources = dict(trusted_sources)

    def ingest(self, *, source_id: str, payloads: Any) -> dict[str, Any]:
        config = self.trusted_sources.get(source_id)
        if not isinstance(config, Mapping):
            raise ValueError("calendar source is not configured")
        events = normalize_calendar_batch(
            payloads,
            trusted_source_id=source_id,
            trusted_source_tier=config.get("source_tier"),
            trusted_source_hosts=config.get("allowed_hosts"),
        )
        inserted = self.store.append_batch(events)
        return {
            "source_id": source_id,
            "received": len(events),
            "inserted": inserted,
            "duplicates_ignored": len(events) - inserted,
            "source_keys": [event.source_key for event in events],
            "durable_store": "LOCAL_SQLITE_SINGLE_RUNTIME",
            "execution_authorized": False,
        }
