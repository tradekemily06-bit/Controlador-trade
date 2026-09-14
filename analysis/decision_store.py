from __future__ import annotations

import os
import sqlite3
from dataclasses import fields
from pathlib import Path
from threading import Lock

from analysis.decision_record import DecisionRecord


class DecisionStore:
    """Optional SQLite persistence for local learning/decision memory.

    This store is intentionally not the production multi-tenant data plane.
    When a database is configured, schema/write failures are surfaced instead
    of silently pretending that durable history was saved.
    """

    _COLUMNS = tuple(field.name for field in fields(DecisionRecord))
    _MIGRATIONS = {"subject_id": "TEXT", "tenant_id": "TEXT"}

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path if database_path is not None else os.environ.get("CONTROLADOR_DECISION_DB")
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
            columns = ", ".join([
                "decision_id TEXT PRIMARY KEY", "created_at TEXT NOT NULL", "symbol TEXT",
                "timeframe TEXT", "signal TEXT NOT NULL", "score REAL NOT NULL",
                "confirmed INTEGER NOT NULL", "reason TEXT NOT NULL",
                "execution_allowed INTEGER NOT NULL", "outcome TEXT",
                "subject_id TEXT", "tenant_id TEXT",
            ])
            with self._lock, self._connect() as connection:
                connection.execute(f"CREATE TABLE IF NOT EXISTS decisions ({columns})")
                existing = {row[1] for row in connection.execute("PRAGMA table_info(decisions)").fetchall()}
                for name, sql_type in self._MIGRATIONS.items():
                    if name not in existing:
                        connection.execute(f"ALTER TABLE decisions ADD COLUMN {name} {sql_type}")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at)")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON decisions(tenant_id)")
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeError("decision storage could not be initialized") from exc

    def _save_values(self, connection: sqlite3.Connection, records: list[DecisionRecord]) -> None:
        placeholders = ", ".join("?" for _ in self._COLUMNS)
        columns = ", ".join(self._COLUMNS)
        connection.executemany(
            f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
            [tuple(record.to_dict()[column] for column in self._COLUMNS) for record in records],
        )

    def save(self, record: DecisionRecord) -> None:
        self.save_many([record])

    def save_many(self, records: list[DecisionRecord]) -> None:
        """Persist a batch atomically when durable local storage is configured."""
        if not records or not self.database_path:
            return
        try:
            with self._lock, self._connect() as connection:
                self._save_values(connection, records)
        except sqlite3.Error as exc:
            raise RuntimeError("decision storage batch write failed") from exc

    def load(self) -> list[DecisionRecord]:
        if not self.database_path:
            return []
        columns = ", ".join(self._COLUMNS)
        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(f"SELECT {columns} FROM decisions ORDER BY created_at ASC").fetchall()
            return [DecisionRecord(
                decision_id=row[0], created_at=row[1], symbol=row[2], timeframe=row[3],
                signal=row[4], score=float(row[5]), confirmed=bool(row[6]), reason=row[7],
                execution_allowed=bool(row[8]), outcome=row[9], subject_id=row[10], tenant_id=row[11],
            ) for row in rows]
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise RuntimeError("decision storage read failed") from exc
