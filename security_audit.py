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
    Local development may use the in-memory fallback, but public SaaS requires
    a durable audit database so a storage failure cannot silently erase the
    security trail. The current SQLite provider is single-instance only, so a
    declared multi-instance public deployment fails closed rather than splitting
    the security trail across independent nodes.
    """

    def __init__(
        self,
        max_events: int = MAX_SECURITY_EVENTS,
        database_path: str | None = None,
        *,
        require_durable: bool | None = None,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events deve ser positivo")
        self.max_events = max_events
        self._salt = secrets.token_bytes(32)
        self._events: deque[SecurityEvent] = deque(maxlen=max_events)
        self._database_path = database_path if database_path is not None else os.environ.get("CONTROLADOR_SECURITY_AUDIT_DB")
        self._require_durable = self._public_saas_mode() if require_durable is None else bool(require_durable)
        self._db_lock = Lock()
        if self._require_durable and self._multi_instance_mode():
            raise RuntimeError("shared security audit provider is required for multi-instance SaaS")
        if self._require_durable and not self._database_path:
            raise RuntimeError("durable security audit provider is required")
        if self._database_path:
            self._initialize_database()

    @staticmethod
    def _public_saas_mode() -> bool:
        return os.environ.get("CONTROLADOR_SAAS_PUBLIC", "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _multi_instance_mode() -> bool:
        return os.environ.get("CONTROLADOR_MULTI_INSTANCE", "").strip().lower() in {"1", "true", "yes", "on"}

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path or ":memory:", timeout=5)

    def _initialize_database(self) -> None:
        try:
            path = Path(self._database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            with self._db_lock, self._connect() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
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
        except (OSError, sqlite3.Error) as exc:
            self._database_path = None
            if self._require_durable:
                raise RuntimeError("durable security audit storage could not be initialized") from exc

    def record(self, *, request_id: str, method: str, path: str, status: int, client_key: str) -> None:
        digest = hashlib.sha256(self._salt + client_key.encode("utf-8", "replace")).hexdigest()
        event = SecurityEvent(time.time(), request_id, method, path[:512], int(status), digest)
        if self._require_durable and not self._database_path:
            raise RuntimeError("durable security audit provider is unavailable")
        if self._database_path:
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
            except sqlite3.Error as exc:
                if self._require_durable:
                    raise RuntimeError("durable security audit write failed") from exc
                self._events.append(event)
                return
        self._events.append(event)

    def snapshot(self) -> list[dict[str, object]]:
        if self._database_path:
            try:
                with self._db_lock, self._connect() as connection:
                    rows = connection.execute(
                        "SELECT timestamp, request_id, method, path, status, client_hash FROM security_events ORDER BY id ASC"
                    ).fetchall()
                return [asdict(SecurityEvent(*row)) for row in rows]
            except sqlite3.Error as exc:
                if self._require_durable:
                    raise RuntimeError("durable security audit read failed") from exc
        if self._require_durable:
            raise RuntimeError("durable security audit provider is unavailable")
        return [asdict(event) for event in self._events]


AUDIT = SecurityAudit()
