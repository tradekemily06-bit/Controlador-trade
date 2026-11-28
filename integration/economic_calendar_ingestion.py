"""Durable local economic-calendar ingestion boundary.

Adapters and schedulers are injected by the host. This module normalizes
publisher payloads with trusted source policy and stores append-only
observations; it does not fetch arbitrary URLs or invent missing values.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

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
        with closing(self._connect()) as connection, connection:
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
        with closing(self._connect()) as connection, connection:
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
        def utc_iso(value: str) -> str:
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError("time range must use ISO-8601 timestamps") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("time range timestamps must include a timezone")
            return parsed.astimezone(timezone.utc).isoformat()

        start = utc_iso(start_at) if isinstance(start_at, str) else ""
        end = utc_iso(end_at) if isinstance(end_at, str) else ""
        if not start or not end or start > end:
            raise ValueError("a valid inclusive time range is required")
        with closing(self._connect()) as connection:
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



class EconomicCalendarPollingWorker:
    """Poll only host-injected official-source adapters and persist observations.

    This worker never accepts feed URLs or publisher identity from request
    payloads. The host supplies a fetcher for each source already present in
    EconomicCalendarIngestionService.trusted_sources. It is process-lifetime
    infrastructure; production continuity still requires hosted supervision.
    """

    def __init__(
        self,
        service: EconomicCalendarIngestionService,
        fetchers: Mapping[str, Callable[[], Any]],
        *,
        interval_seconds: float = 300.0,
    ) -> None:
        if not isinstance(service, EconomicCalendarIngestionService):
            raise TypeError("an economic calendar ingestion service is required")
        if not isinstance(fetchers, Mapping) or not fetchers:
            raise ValueError("at least one configured calendar source fetcher is required")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(float(interval_seconds))
            or interval_seconds < 15
            or interval_seconds > 86400
        ):
            raise ValueError("interval_seconds must be between 15 and 86400")
        normalized: dict[str, Callable[[], Any]] = {}
        for source_id, fetcher in fetchers.items():
            if (
                not isinstance(source_id, str)
                or source_id not in service.trusted_sources
                or not callable(fetcher)
            ):
                raise ValueError("every fetcher must map to a trusted configured source")
            normalized[source_id] = fetcher
        self.service = service
        self.fetchers = normalized
        self.interval_seconds = float(interval_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cycle_at: str | None = None
        self._last_worker_error: str | None = None
        self._source_status: dict[str, dict[str, Any]] = {
            source_id: {"state": "NOT_RUN", "inserted": 0, "received": 0, "last_success_at": None}
            for source_id in normalized
        }

    def run_once(self) -> dict[str, dict[str, Any]]:
        for source_id, fetcher in self.fetchers.items():
            try:
                payloads = fetcher()
                result = self.service.ingest(source_id=source_id, payloads=payloads)
            except Exception as exc:
                with self._lock:
                    self._source_status[source_id] = {
                        **self._source_status[source_id],
                        "state": "SOURCE_UNAVAILABLE",
                        "last_error_class": type(exc).__name__,
                    }
                continue
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._source_status[source_id] = {
                    "state": "INGESTED" if result["inserted"] else "NO_NEW_OBSERVATIONS",
                    "received": result["received"],
                    "inserted": result["inserted"],
                    "duplicates_ignored": result["duplicates_ignored"],
                    "last_success_at": now,
                    "last_error_class": None,
                }
        with self._lock:
            self._last_cycle_at = datetime.now(timezone.utc).isoformat()
            return {key: dict(value) for key, value in self._source_status.items()}

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="controlador-economic-calendar-poller",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                self._last_worker_error = None
            except Exception as exc:
                self._last_worker_error = type(exc).__name__
            self._stop.wait(self.interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout < 0
            or timeout > 60
        ):
            raise ValueError("timeout must be finite and between 0 and 60 seconds")
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=float(timeout))
            with self._lock:
                if self._thread is thread and not thread.is_alive():
                    self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "configured": True,
                "worker_running": bool(self._thread is not None and self._thread.is_alive()),
                "interval_seconds": self.interval_seconds,
                "source_count": len(self.fetchers),
                "last_cycle_at": self._last_cycle_at,
                "worker_error_class": self._last_worker_error,
                "sources": {key: dict(value) for key, value in self._source_status.items()},
                "execution_authorized": False,
            }
