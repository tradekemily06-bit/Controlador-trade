from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import time
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class NotificationOutboxItem:
    idempotency_key: str
    payload: dict[str, Any]
    attempts: int
    lease_token: str


@dataclass(frozen=True)
class NotificationDispatchResult:
    claimed: int
    delivered: int
    retried: int
    dead_lettered: int


def redact_delivery_error(error: object) -> str:
    """Bound diagnostics and remove URLs, auth values and common secret fields."""
    value = str(error)[:2000]
    value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)(authorization|token|secret|password|api[_-]?key|private[_-]?key)"
        r"(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        value,
    )
    value = re.sub(r"https?://[^\s'\"<>]+", "[URL REDACTED]", value)
    value = re.sub(r"(?i)(p256dh|auth)(\s*[:=]\s*)([^\s,;]+)", r"\1\2[REDACTED]", value)
    return value[:500]

class NotificationSink(Protocol):
    """External destination; implementations must honor the idempotency key."""

    def deliver(self, idempotency_key: str, payload: Mapping[str, Any]) -> None:
        ...


class PersistentNotificationOutbox:
    """SQLite outbox for at-least-once external notification delivery.

    The outbox persists intent and retry state; it does not send network
    requests itself. A configured worker and sink must call dispatch_due.
    Destinations should deduplicate by idempotency_key because a process may
    stop after remote acceptance but before the local success receipt is saved.
    """

    def __init__(self, path: str | Path, *, max_attempts: int = 8,
                 base_backoff_seconds: float = 5.0,
                 max_backoff_seconds: float = 900.0) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if base_backoff_seconds <= 0 or max_backoff_seconds < base_backoff_seconds:
            raise ValueError("invalid notification retry backoff")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max_attempts
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    idempotency_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('PENDING', 'IN_FLIGHT', 'DELIVERED', 'DEAD')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL,
                    lease_until REAL,
                    lease_token TEXT,
                    created_at REAL NOT NULL,
                    delivered_at REAL,
                    last_error TEXT
                )
                """
            )
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(notification_outbox)").fetchall()}
            if "lease_token" not in columns:
                db.execute("ALTER TABLE notification_outbox ADD COLUMN lease_token TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_notification_outbox_due "
                "ON notification_outbox(status, available_at, lease_until)"
            )

    def enqueue(self, idempotency_key: str, payload: Mapping[str, Any], *,
                now: float | None = None) -> bool:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        encoded = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
        current = time() if now is None else float(now)
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO notification_outbox
                    (idempotency_key, payload_json, status, attempts,
                     available_at, created_at)
                VALUES (?, ?, 'PENDING', 0, ?, ?)
                """,
                (idempotency_key.strip(), encoded, current, current),
            )
        return cursor.rowcount == 1

    def claim_due(self, *, limit: int = 50, now: float | None = None,
                  lease_seconds: float = 60.0) -> tuple[NotificationOutboxItem, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = time() if now is None else float(now)
        claimed: list[NotificationOutboxItem] = []
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """
                SELECT idempotency_key, payload_json, attempts
                FROM notification_outbox
                WHERE (status = 'PENDING' AND available_at <= ?)
                   OR (status = 'IN_FLIGHT' AND lease_until <= ?)
                ORDER BY created_at, idempotency_key
                LIMIT ?
                """,
                (current, current, limit),
            ).fetchall()
            for row in rows:
                attempts = int(row["attempts"]) + 1
                lease_token = uuid.uuid4().hex
                db.execute(
                    """
                    UPDATE notification_outbox
                    SET status='IN_FLIGHT', attempts=?, lease_until=?, lease_token=?, last_error=NULL
                    WHERE idempotency_key=?
                    """,
                    (attempts, current + lease_seconds, lease_token, row["idempotency_key"]),
                )
                claimed.append(
                    NotificationOutboxItem(
                        idempotency_key=str(row["idempotency_key"]),
                        payload=json.loads(row["payload_json"]),
                        attempts=attempts,
                        lease_token=lease_token,
                    )
                )
            db.commit()
        return tuple(claimed)

    def mark_delivered(self, idempotency_key: str, lease_token: str, *, now: float | None = None) -> bool:
        current = time() if now is None else float(now)
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """
                UPDATE notification_outbox
                SET status='DELIVERED', delivered_at=?, lease_until=NULL, lease_token=NULL, last_error=NULL
                WHERE idempotency_key=? AND status='IN_FLIGHT' AND lease_token=?
                """,
                (current, idempotency_key, lease_token),
            )
        return cursor.rowcount == 1

    def mark_failed(self, idempotency_key: str, lease_token: str, error: str, *,
                    now: float | None = None) -> str:
        current = time() if now is None else float(now)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT attempts FROM notification_outbox "
                "WHERE idempotency_key=? AND status='IN_FLIGHT' AND lease_token=?",
                (idempotency_key, lease_token),
            ).fetchone()
            if row is None:
                raise ValueError("notification is not currently in flight")
            attempts = int(row["attempts"])
            if attempts >= self.max_attempts:
                status = "DEAD"
                available_at = current
            else:
                status = "PENDING"
                delay = min(
                    self.base_backoff_seconds * (2 ** max(0, attempts - 1)),
                    self.max_backoff_seconds,
                )
                available_at = current + delay
            db.execute(
                """
                UPDATE notification_outbox
                SET status=?, available_at=?, lease_until=NULL, lease_token=NULL, last_error=?
                WHERE idempotency_key=? AND status='IN_FLIGHT' AND lease_token=?
                """,
                (status, available_at, redact_delivery_error(error), idempotency_key, lease_token),
            )
        return status

    def dispatch_due(self, sink: NotificationSink, *, limit: int = 50,
                     now: float | None = None, lease_seconds: float = 60.0) -> NotificationDispatchResult:
        if not callable(getattr(sink, "deliver", None)):
            raise ValueError("sink must provide deliver(idempotency_key, payload)")
        claimed = self.claim_due(limit=limit, now=now, lease_seconds=lease_seconds)
        delivered = retried = dead_lettered = 0
        for item in claimed:
            try:
                sink.deliver(item.idempotency_key, item.payload)
            except Exception as exc:
                status = self.mark_failed(item.idempotency_key, item.lease_token, str(exc), now=now)
                if status == "DEAD":
                    dead_lettered += 1
                else:
                    retried += 1
            else:
                if self.mark_delivered(item.idempotency_key, item.lease_token, now=now):
                    delivered += 1
        return NotificationDispatchResult(
            claimed=len(claimed),
            delivered=delivered,
            retried=retried,
            dead_lettered=dead_lettered,
        )

    def status_counts(self) -> dict[str, int]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS total FROM notification_outbox GROUP BY status"
            ).fetchall()
        counts = {"PENDING": 0, "IN_FLIGHT": 0, "DELIVERED": 0, "DEAD": 0}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        return counts
