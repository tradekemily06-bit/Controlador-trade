from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Mapping, Protocol

from security.tenant_context import TenantContext
from security.sqlite_tenant_storage import SQLiteTenantStorage


@dataclass(frozen=True)
class TenantOutboxItem:
    idempotency_key: str
    tenant_id: str
    subject_id: str
    notification_id: str
    payload: dict[str, Any]
    attempts: int
    lease_token: str


@dataclass(frozen=True)
class TenantOutboxDispatchResult:
    claimed: int
    delivered: int
    retried: int
    dead_lettered: int


class TenantNotificationSink(Protocol):
    """Transport must route only to the explicit tenant/subject recipient."""
    def deliver(self, idempotency_key: str, recipient: Mapping[str, str],
                payload: Mapping[str, Any]) -> None: ...


class TenantNotificationOutbox:
    """Tenant/subject-isolated transactional inbox + external-delivery outbox.

    Inbox append and outbox insert share one SQLite transaction. This is a
    single-host foundation; multi-replica deployment requires shared SQL
    transactions and distributed lease fencing.
    """

    def __init__(self, storage: SQLiteTenantStorage, *, max_attempts: int = 8,
                 base_backoff_seconds: float = 5.0,
                 max_backoff_seconds: float = 900.0) -> None:
        if not isinstance(storage, SQLiteTenantStorage):
            raise TypeError("SQLiteTenantStorage is required")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if base_backoff_seconds <= 0 or max_backoff_seconds < base_backoff_seconds:
            raise ValueError("invalid retry backoff")
        self.storage = storage
        self.max_attempts = max_attempts
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        with self.storage._lock, self.storage._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tenant_notification_outbox (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    notification_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PENDING','IN_FLIGHT','DELIVERED','DEAD')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL,
                    lease_until REAL,
                    lease_token TEXT,
                    created_at REAL NOT NULL,
                    delivered_at REAL,
                    last_error TEXT,
                    PRIMARY KEY (tenant_id, subject_id, notification_id)
                )
            """)
            db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_notification_due
                ON tenant_notification_outbox(status, available_at, lease_until)""")

    def publish(self, context: TenantContext, notification: Mapping[str, Any],
                *, inbox_key: str = "ecosystem:notifications", inbox_limit: int = 500,
                now: float | None = None) -> bool:
        tenant_id, subject_id, _ = self.storage._scope(context, inbox_key)
        if not isinstance(notification, Mapping):
            raise ValueError("notification must be an object")
        notification_id = notification.get("notification_id")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification_id is required")
        if isinstance(inbox_limit, bool) or not isinstance(inbox_limit, int) or not 1 <= inbox_limit <= 2000:
            raise ValueError("inbox_limit must be between 1 and 2000")
        encoded = json.dumps(dict(notification), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        current = time() if now is None else float(now)
        with self.storage._lock, self.storage._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, inbox_key.strip()),
            ).fetchone()
            inbox = [] if row is None else json.loads(row[0])
            if not isinstance(inbox, list) or any(not isinstance(item, dict) for item in inbox):
                raise ValueError("stored tenant inbox has invalid shape")
            if any(item.get("notification_id") == notification_id for item in inbox):
                db.rollback()
                return False
            inbox.append(json.loads(encoded))
            db.execute("""
                INSERT INTO tenant_state(tenant_id, subject_id, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, subject_id, key) DO UPDATE SET
                    value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP
            """, (tenant_id, subject_id, inbox_key.strip(),
                  json.dumps(inbox[-inbox_limit:], ensure_ascii=False, separators=(",", ":"))))
            cursor = db.execute("""
                INSERT OR IGNORE INTO tenant_notification_outbox
                (tenant_id, subject_id, notification_id, payload_json, status,
                 attempts, available_at, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', 0, ?, ?)
            """, (tenant_id, subject_id, notification_id, encoded, current, current))
            if cursor.rowcount != 1:
                raise RuntimeError("tenant inbox/outbox idempotency boundary is inconsistent")
            db.commit()
        return True

    def claim_due(self, *, limit: int = 50, now: float | None = None,
                  lease_seconds: float = 60.0) -> tuple[TenantOutboxItem, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or lease_seconds <= 0:
            raise ValueError("invalid claim limit or lease")
        current = time() if now is None else float(now)
        claimed: list[TenantOutboxItem] = []
        with self.storage._lock, self.storage._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                UPDATE tenant_notification_outbox SET status='DEAD', lease_until=NULL,
                    lease_token=NULL, last_error='delivery lease expired; retry budget exhausted'
                WHERE status='IN_FLIGHT' AND lease_until <= ? AND attempts >= ?
            """, (current, self.max_attempts))
            rows = db.execute("""
                SELECT tenant_id, subject_id, notification_id, payload_json, attempts
                FROM tenant_notification_outbox
                WHERE (status='PENDING' AND available_at <= ?)
                   OR (status='IN_FLIGHT' AND lease_until <= ?)
                ORDER BY created_at, tenant_id, subject_id, notification_id LIMIT ?
            """, (current, current, limit)).fetchall()
            for row in rows:
                attempts = int(row["attempts"]) + 1
                token = uuid.uuid4().hex
                db.execute("""
                    UPDATE tenant_notification_outbox SET status='IN_FLIGHT',
                        attempts=?, lease_until=?, lease_token=?, last_error=NULL
                    WHERE tenant_id=? AND subject_id=? AND notification_id=?
                """, (attempts, current + lease_seconds, token, row["tenant_id"],
                      row["subject_id"], row["notification_id"]))
                claimed.append(TenantOutboxItem(
                    idempotency_key=hashlib.sha256(json.dumps([row["tenant_id"], row["subject_id"], row["notification_id"]], separators=(",", ":")).encode("utf-8")).hexdigest(),
                    tenant_id=str(row["tenant_id"]), subject_id=str(row["subject_id"]),
                    notification_id=str(row["notification_id"]),
                    payload=json.loads(row["payload_json"]), attempts=attempts, lease_token=token,
                ))
            db.commit()
        return tuple(claimed)

    def _finish(self, item: TenantOutboxItem, *, status: str, now: float) -> bool:
        with self.storage._lock, self.storage._connect() as db:
            cursor = db.execute("""
                UPDATE tenant_notification_outbox SET status=?, delivered_at=?,
                    lease_until=NULL, lease_token=NULL, last_error=NULL
                WHERE tenant_id=? AND subject_id=? AND notification_id=?
                  AND status='IN_FLIGHT' AND lease_token=? AND lease_until > ?
            """, (status, now if status == "DELIVERED" else None, item.tenant_id,
                  item.subject_id, item.notification_id, item.lease_token, now))
        return cursor.rowcount == 1

    def mark_failed(self, item: TenantOutboxItem, error: object, *, now: float) -> str:
        with self.storage._lock, self.storage._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""
                SELECT attempts FROM tenant_notification_outbox
                WHERE tenant_id=? AND subject_id=? AND notification_id=?
                  AND status='IN_FLIGHT' AND lease_token=? AND lease_until > ?
            """, (item.tenant_id, item.subject_id, item.notification_id, item.lease_token, now)).fetchone()
            if row is None:
                raise ValueError("tenant notification lease ownership was lost")
            attempts = int(row["attempts"])
            status = "DEAD" if attempts >= self.max_attempts else "PENDING"
            delay = min(self.base_backoff_seconds * (2 ** max(0, attempts - 1)), self.max_backoff_seconds)
            message = str(error)[:300].replace("\\n", " ")
            import re
            message = re.sub(r"(?i)bearer\s+\S+|https?://\S+|(?:token|secret|password|api[_-]?key)\s*[:=]\s*\S+",
                             "[REDACTED]", message)[:300]
            cursor = db.execute("""
                UPDATE tenant_notification_outbox SET status=?, available_at=?,
                    lease_until=NULL, lease_token=NULL, last_error=?
                WHERE tenant_id=? AND subject_id=? AND notification_id=?
                  AND status='IN_FLIGHT' AND lease_token=? AND lease_until > ?
            """, (status, now if status == "DEAD" else now + delay, message,
                  item.tenant_id, item.subject_id, item.notification_id, item.lease_token, now))
            if cursor.rowcount != 1:
                raise ValueError("tenant notification lease ownership was lost")
            db.commit()
        return status

    def dispatch_due(self, sink: TenantNotificationSink, *, limit: int = 50,
                     now: float | None = None, lease_seconds: float = 60.0) -> TenantOutboxDispatchResult:
        if not callable(getattr(sink, "deliver", None)):
            raise ValueError("tenant sink must implement deliver")
        current = time() if now is None else float(now)
        items = self.claim_due(limit=limit, now=current, lease_seconds=lease_seconds)
        delivered = retried = dead = 0
        for item in items:
            recipient = {"tenant_id": item.tenant_id, "subject_id": item.subject_id}
            try:
                sink.deliver(item.idempotency_key, recipient, item.payload)
            except Exception as exc:
                try:
                    status = self.mark_failed(item, exc, now=current)
                except ValueError:
                    continue
                if status == "DEAD": dead += 1
                else: retried += 1
            else:
                if self._finish(item, status="DELIVERED", now=current):
                    delivered += 1
        return TenantOutboxDispatchResult(len(items), delivered, retried, dead)

    def status_counts(self, context: TenantContext | None = None) -> dict[str, int]:
        where = ""
        params: tuple[Any, ...] = ()
        if context is not None:
            tenant_id, subject_id, _ = self.storage._scope(context, "tenant-outbox-status")
            where = " WHERE tenant_id=? AND subject_id=?"
            params = (tenant_id, subject_id)
        with self.storage._lock, self.storage._connect() as db:
            rows = db.execute("SELECT status, COUNT(*) total FROM tenant_notification_outbox" + where + " GROUP BY status", params).fetchall()
        counts = {"PENDING": 0, "IN_FLIGHT": 0, "DELIVERED": 0, "DEAD": 0}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        return counts
