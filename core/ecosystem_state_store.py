from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
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
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_history_quarantine (
                    archive_id TEXT PRIMARY KEY,
                    archived_at TEXT NOT NULL,
                    corruption_category TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    raw_payload TEXT NOT NULL
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

    def _write_state(self, key: str, value: Any) -> None:
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

    def save(self, key: str, value: Any) -> None:
        # Notification history has a dedicated guarded writer. Keeping the
        # generic state API from writing that key prevents bypassing corruption
        # protection after a damaged history has been detected.
        if key == "notifications":
            raise ValueError("use save_notifications para persistir o histórico")
        self._write_state(key, value)

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

    def mark_notifications_unavailable(self, category: str) -> None:
        """Prevent routine writes after validation detects damaged history."""
        allowed = {"invalid_json", "read_failed", "invalid_shape", "invalid_records"}
        normalized = str(category).strip().lower()
        if normalized not in allowed:
            raise ValueError("categoria de histórico inválida")
        self._notifications_load_error = normalized

    def archive_notifications_for_recovery(self, *, confirmed: bool = False) -> dict[str, str]:
        """Preserve the exact damaged payload before any separately approved recovery."""
        if confirmed is not True:
            raise ValueError("confirmação explícita é obrigatória para arquivar o histórico")
        category = self._notifications_load_error
        allowed = {"invalid_json", "read_failed", "invalid_shape", "invalid_records"}
        if category not in allowed:
            raise NotificationHistoryUnavailableError(
                "não há histórico marcado para recuperação"
            )

        archive_id = str(uuid.uuid4())
        archived_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock, self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT value_json FROM ecosystem_state WHERE key = ?",
                    ("notifications",),
                ).fetchone()
                if row is None:
                    raise NotificationHistoryUnavailableError(
                        "payload original de notificações não encontrado; nada foi alterado"
                    )
                raw_payload = row[0]
                digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
                db.execute(
                    """
                    INSERT INTO notification_history_quarantine
                    (archive_id, archived_at, corruption_category, payload_sha256, raw_payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (archive_id, archived_at, category, digest, raw_payload),
                )
        except sqlite3.Error as exc:
            raise NotificationHistoryUnavailableError(
                "não foi possível preservar o histórico original; nenhum reparo foi aplicado"
            ) from exc

        # Deliberately keep the original row and the unavailable flag untouched.
        return {
            "archive_id": archive_id,
            "archived_at": archived_at,
            "corruption_category": category,
            "payload_sha256": digest,
        }

    def save_notifications(self, notifications: list[dict[str, Any]]) -> None:
        # Preserve damaged evidence until an explicit recovery procedure has
        # inspected it. A routine publish must not silently replace corrupt data.
        if self._notifications_load_error is not None:
            raise NotificationHistoryUnavailableError(
                "histórico de notificações exige recuperação explícita antes de nova gravação"
            )
        try:
            self._write_state("notifications", notifications)
        except sqlite3.Error as exc:
            raise NotificationHistoryUnavailableError(
                "persistência do histórico de notificações indisponível"
            ) from exc
