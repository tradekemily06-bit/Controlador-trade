from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

MAX_SECURITY_EVENTS = 1000


@dataclass(frozen=True)
class SecurityEvent:
    timestamp: float
    request_id: str
    method: str
    path: str
    status: int
    client_hash: str


class SecurityAudit:
    """Bounded, privacy-conscious security event trail.

    Stores no raw IP, credentials, authorization tokens or request bodies.
    When CONTROLADOR_SECURITY_AUDIT_DB is configured, events are also retained
    in a local SQLite store with the same bounded retention policy. A failed
    persistence write never turns the security audit into an application outage;
    the in-memory trail remains available. Centralized multi-instance storage
    still belongs to the production deployment boundary.
    """

    def __init__(self, max_events: int = MAX_SECURITY_EVENTS, database_path: str | None = None) -> None:
        if max_events < 1:
            raise ValueError("max_events deve ser positivo")
        self.max_events = max_events
        self._salt = secrets.token_bytes(32)
        self._events: deque[SecurityEvent] = deque(maxlen=max_events)
        self._database_path = database_path if database_path is not None else os.environ.get("CONTROLADOR_SECURITY_AUDIT_DB")
        self._db_lock = Lock()
        if self._database_path:
            self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path or ":memory:", timeout=5)

    def _initialize_database(self) -> None:
        try:
            path = Path(self._database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            with self._db_lock, self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS security_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        request_id TEXT NOT NULL,
                        method TEXT NOT NULL,
                        path TEXT NOT NULL,
                        status INTEGER NOT NULL,
                        client_hash TEXT NOT NULL
                    )
                    """
                )
        except (OSError, sqlite3.Error):
            self._database_path = None

    def record(self, *, request_id: str, method: str, path: str, status: int, client_key: str) -> None:
        digest = hashlib.sha256(self._salt + client_key.encode("utf-8", "replace")).hexdigest()
        event = SecurityEvent(time.time(), request_id, method, path[:512], int(status), digest)
        self._events.append(event)
        if not self._database_path:
            return
        try:
            with self._db_lock, self._connect() as connection:
                connection.execute(
                    "INSERT INTO security_events (timestamp, request_id, method, path, status, client_hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (event.timestamp, event.request_id, event.method, event.path, event.status, event.client_hash),
                )
                connection.execute(
                    "DELETE FROM security_events WHERE id NOT IN (SELECT id FROM security_events ORDER BY id DESC LIMIT ?)",
                    (self.max_events,),
                )
        except sqlite3.Error:
            pass

    def snapshot(self) -> list[dict[str, object]]:
        if self._database_path:
            try:
                with self._db_lock, self._connect() as connection:
                    rows = connection.execute(
                        "SELECT timestamp, request_id, method, path, status, client_hash FROM security_events ORDER BY id ASC"
                    ).fetchall()
                return [asdict(SecurityEvent(*row)) for row in rows]
            except sqlite3.Error:
                pass
        return [asdict(event) for event in self._events]


AUDIT = SecurityAudit()
