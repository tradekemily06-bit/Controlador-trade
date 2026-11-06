from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class NotificationHistoryUnavailableError(RuntimeError):
    """Notification history cannot be safely persisted or replaced."""


class EcosystemStateStore:
    """Durable single-runtime store for user-facing ecosystem state.

    Trading authority remains outside this store. It persists user preferences,
    notifications, and educational records so all clients of the same runtime
    observe the same state after restarts. Learning records never grant trading
    authority.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._notifications_load_error: str | None = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ecosystem_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                )
                """
            )

    def load(self, key: str) -> Any | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT value_json FROM ecosystem_state WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def save(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=lambda item: item.value if isinstance(item, Enum) else str(item))
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO ecosystem_state(key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json
                """,
                (key, encoded),
            )

    def load_learning(self) -> dict[str, Any] | None:
        value = self.load("learning")
        return value if isinstance(value, dict) else None

    def save_learning(self, learning: dict[str, Any]) -> None:
        self.save("learning", learning)

    def load_preferences(self) -> dict[str, Any] | None:
        value = self.load("preferences")
        return value if isinstance(value, dict) else None

    def save_preferences(self, preferences: Any) -> None:
        self.save("preferences", asdict(preferences))

    @property
    def notifications_load_error(self) -> str | None:
        """Return a safe category when persisted notification JSON is corrupt."""
        return self._notifications_load_error

    def load_notifications(self) -> list[dict[str, Any]]:
        self._notifications_load_error = None
        try:
            value = self.load("notifications")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._notifications_load_error = "invalid_json"
            return []
        except sqlite3.Error:
            self._notifications_load_error = "read_failed"
            return []
        if value is None:
            return []
        if not isinstance(value, list):
            self._notifications_load_error = "invalid_shape"
            return []
        if any(not isinstance(item, dict) for item in value):
            self._notifications_load_error = "invalid_records"
        return value

    def save_notifications(self, notifications: list[dict[str, Any]]) -> None:
        # Preserve damaged evidence until an explicit recovery procedure has
        # inspected it. A routine publish must not silently replace corrupt data.
        if self._notifications_load_error is not None:
            raise NotificationHistoryUnavailableError(
                "histórico de notificações exige recuperação explícita antes de nova gravação"
            )
        try:
            self.save("notifications", notifications)
        except sqlite3.Error as exc:
            raise NotificationHistoryUnavailableError(
                "persistência do histórico de notificações indisponível"
            ) from exc
