from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class EcosystemStateStore:
    """Durable single-runtime store for user-facing ecosystem state.

    Trading authority remains outside this store. The store only persists
    preferences and notifications so all clients of the same runtime observe
    the same state after restarts.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
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

    def load_preferences(self) -> dict[str, Any] | None:
        value = self.load("preferences")
        return value if isinstance(value, dict) else None

    def save_preferences(self, preferences: Any) -> None:
        self.save("preferences", asdict(preferences))

    def load_notifications(self) -> list[dict[str, Any]]:
        value = self.load("notifications")
        return value if isinstance(value, list) else []

    def save_notifications(self, notifications: list[dict[str, Any]]) -> None:
        self.save("notifications", notifications)
