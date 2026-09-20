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
MAX_SECURITY_REQUEST_ID_LENGTH = 128
MAX_SECURITY_METHOD_LENGTH = 16
MAX_SECURITY_PATH_LENGTH = 512
MAX_SECURITY_CLIENT_KEY_LENGTH = 256


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
        if self._database_path:
            path = Path(self._database_path)
            if path.parent.resolve(strict=True) != path.parent.absolute():
                raise RuntimeError("security audit database directory must not be a symlink")
            if path.exists():
                stat = path.lstat()
                if path.is_symlink() or not path.is_file():
                    raise RuntimeError("security audit database must be a regular file")
        return sqlite3.connect(self._database_path or ":memory:", timeout=5)

    def _initialize_database(self) -> None:
        try:
            path = Path(self._database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            if path.parent.resolve(strict=True) != path.parent.absolute():
                raise OSError("security audit database directory must not be a symlink")
            if path.exists():
                stat = path.lstat()
                if path.is_symlink() or not path.is_file():
                    raise OSError("security audit database must be a regular file")
            with self._db_lock, self._connect() as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
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
            # Security audit metadata must not become world-readable through a
            # permissive process umask. The database contains request paths and
            # pseudonymous client identifiers.
            try:
                os.chmod(path, 0o600)
            except OSError as exc:
                raise OSError("security audit database permissions could not be hardened") from exc
        except (OSError, sqlite3.Error) as exc:
            self._database_path = None
            if self._require_durable:
                raise RuntimeError("durable security audit storage could not be initialized") from exc

    def record(self, *, request_id: str, method: str, path: str, status: int, client_key: str) -> None:
        # Audit input is an internal boundary, but it must remain bounded even
        # when called outside the HTTP layer. Otherwise a malformed request_id
        # or client_key could inflate the durable trail before retention pruning.
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > MAX_SECURITY_REQUEST_ID_LENGTH:
            raise ValueError("request_id de auditoria inválido ou excede o limite permitido")
        if not isinstance(method, str) or not method.strip() or len(method) > MAX_SECURITY_METHOD_LENGTH:
            raise ValueError("método de auditoria inválido ou excede o limite permitido")
        if not isinstance(path, str) or len(path) > MAX_SECURITY_PATH_LENGTH:
            raise ValueError("caminho de auditoria excede o limite permitido")
        if not isinstance(client_key, str) or len(client_key) > MAX_SECURITY_CLIENT_KEY_LENGTH:
            raise ValueError("identidade do cliente excede o limite permitido")
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise ValueError("status HTTP de auditoria inválido")
        digest = hashlib.sha256(self._salt + client_key.encode("utf-8", "replace")).hexdigest()
        event = SecurityEvent(time.time(), request_id, method.strip().upper(), path, int(status), digest)
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
