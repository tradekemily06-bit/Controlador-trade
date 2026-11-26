from __future__ import annotations

import os
import sqlite3
from dataclasses import fields
from pathlib import Path
from threading import Lock

from analysis.decision_record import DecisionRecord


class DecisionStore:
    """Optional SQLite persistence for the learning/decision memory.

    The store is enabled only when CONTROLADOR_DECISION_DB is configured.
    Without it, the application keeps its existing in-memory behavior.
    Persistence failures are fail-soft: the caller can continue using the
    in-memory memory without turning a storage problem into an outage.
    """

    _COLUMNS = tuple(field.name for field in fields(DecisionRecord))

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path if database_path is not None else os.environ.get("CONTROLADOR_DECISION_DB")
        self._lock = Lock()
        self._persistence_state = (
            "INITIALIZING" if self.database_path else "IN_MEMORY_NOT_CONFIGURED"
        )
        self._last_error: str | None = None
        if self.database_path:
            self._initialize()

    def persistence_status(self) -> dict[str, str | bool | None]:
        """Expose durable-memory state without leaking paths or exception details."""
        configured = bool(self.database_path)
        return {
            "configured": configured,
            "mode": "SQLITE" if configured else "IN_MEMORY",
            "state": self._persistence_state,
            "last_error_class": self._last_error,
            "durability_confirmed": self._persistence_state == "PERSISTENT_READY",
        }

    def _mark_error(self, exc: BaseException) -> None:
        self._persistence_state = "PERSISTENCE_ERROR"
        self._last_error = type(exc).__name__

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path or ":memory:", timeout=5)

    def _initialize(self) -> None:
        try:
            path = Path(self.database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            columns = ", ".join([
                "decision_id TEXT PRIMARY KEY", "created_at TEXT NOT NULL", "symbol TEXT",
                "timeframe TEXT", "signal TEXT NOT NULL", "score REAL NOT NULL",
                "confirmed INTEGER NOT NULL", "reason TEXT NOT NULL",
                "execution_allowed INTEGER NOT NULL", "outcome TEXT",
            ])
            with self._lock, self._connect() as connection:
                connection.execute(f"CREATE TABLE IF NOT EXISTS decisions ({columns})")
                columns_existing = {row[1] for row in connection.execute("PRAGMA table_info(decisions)").fetchall()}
                if "outcome_source" not in columns_existing:
                    connection.execute("ALTER TABLE decisions ADD COLUMN outcome_source TEXT NOT NULL DEFAULT 'MANUAL_STUDY'")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at)")
            self._persistence_state = "PERSISTENT_READY"
            self._last_error = None
        except (OSError, sqlite3.Error) as exc:
            self._mark_error(exc)

    def save(self, record: DecisionRecord) -> None:
        if not self.database_path or self._persistence_state != "PERSISTENT_READY":
            return
        placeholders = ", ".join("?" for _ in self._COLUMNS)
        columns = ", ".join(self._COLUMNS)
        values = tuple(record.to_dict()[column] for column in self._COLUMNS)
        try:
            with self._lock, self._connect() as connection:
                connection.execute(f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})", values)
        except sqlite3.Error as exc:
            self._mark_error(exc)

    def load(self) -> list[DecisionRecord]:
        if not self.database_path or self._persistence_state != "PERSISTENT_READY":
            return []
        columns = ", ".join(self._COLUMNS)
        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(f"SELECT {columns} FROM decisions ORDER BY created_at ASC").fetchall()
            return [DecisionRecord(
                decision_id=row[0], created_at=row[1], symbol=row[2], timeframe=row[3],
                signal=row[4], score=float(row[5]), confirmed=bool(row[6]), reason=row[7],
                execution_allowed=bool(row[8]), outcome=row[9], outcome_source=row[10] if len(row) > 10 else "MANUAL_STUDY",
            ) for row in rows]
        except (sqlite3.Error, ValueError, TypeError) as exc:
            self._mark_error(exc)
            return []
