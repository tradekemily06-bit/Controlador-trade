"""Persistent multi-device connection state for the trading ecosystem.

A device connection is a session owned by a trusted tenant/subject. Sessions are
independent: connecting a phone does not disconnect a notebook, and changing
devices never implicitly logs another device out. A session ends only when that
device is explicitly disconnected (or an explicit security revocation is
implemented by the authenticated control plane).

This module tracks connection state only. It does not grant trading authority,
change the execution safety gates, or replace authentication.

The registry uses local SQLite and is therefore a single-instance primitive.
Multi-instance production must use a shared session provider instead of
silently treating one process-local database as authoritative.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


MULTI_INSTANCE_ENV = "CONTROLADOR_MULTI_INSTANCE"


@dataclass(frozen=True)
class DeviceSession:
    session_id: str
    device_id: str
    device_name: str
    subject_id: str
    tenant_id: str
    connected_at: datetime
    last_seen_at: datetime
    connected: bool = True


class DeviceSessionRegistry:
    """Durable registry allowing multiple independently connected devices."""

    def __init__(self, database_path: str | Path) -> None:
        if os.environ.get(MULTI_INSTANCE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            raise RuntimeError("local device session registry is not safe for multi-instance deployment")
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._lock, sqlite3.connect(self.database_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS device_sessions ("
                "session_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, device_name TEXT NOT NULL, "
                "subject_id TEXT NOT NULL, tenant_id TEXT NOT NULL, connected_at TEXT NOT NULL, "
                "last_seen_at TEXT NOT NULL, connected INTEGER NOT NULL CHECK(connected IN (0,1))"
                ")"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_device_sessions_owner "
                "ON device_sessions(tenant_id, subject_id, connected)"
            )
            db.commit()

    @staticmethod
    def _scope(subject_id: str, tenant_id: str) -> tuple[str, str]:
        subject, tenant = str(subject_id).strip(), str(tenant_id).strip()
        if not subject or not tenant:
            raise PermissionError("trusted tenant and subject are required")
        return subject, tenant

    @staticmethod
    def _utc(value: datetime | None) -> datetime:
        value = value or datetime.now(timezone.utc)
        if value.tzinfo is None:
            raise ValueError("timestamps must include timezone")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _from_row(row: tuple) -> DeviceSession:
        return DeviceSession(
            session_id=row[0], device_id=row[1], device_name=row[2], subject_id=row[3], tenant_id=row[4],
            connected_at=datetime.fromisoformat(row[5]), last_seen_at=datetime.fromisoformat(row[6]), connected=bool(row[7]),
        )

    def connect(self, *, device_id: str, device_name: str, subject_id: str, tenant_id: str, now: datetime | None = None) -> DeviceSession:
        subject, tenant = self._scope(subject_id, tenant_id)
        device_id, device_name = str(device_id).strip(), str(device_name).strip()
        if not device_id or not device_name:
            raise ValueError("device_id and device_name are required")
        timestamp = self._utc(now).isoformat()
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT session_id, device_id, device_name, subject_id, tenant_id, connected_at, last_seen_at, connected "
                "FROM device_sessions WHERE device_id=? AND subject_id=? AND tenant_id=? AND connected=1",
                (device_id, subject, tenant),
            ).fetchone()
            if row is not None:
                db.execute("UPDATE device_sessions SET device_name=?, last_seen_at=? WHERE session_id=?", (device_name, timestamp, row[0]))
                db.commit()
                return self._from_row((row[0], device_id, device_name, subject, tenant, row[5], timestamp, 1))
            session = DeviceSession(f"session-{uuid4().hex}", device_id, device_name, subject, tenant, self._utc(now), self._utc(now), True)
            db.execute(
                "INSERT INTO device_sessions(session_id,device_id,device_name,subject_id,tenant_id,connected_at,last_seen_at,connected) VALUES(?,?,?,?,?,?,?,1)",
                (session.session_id, session.device_id, session.device_name, session.subject_id, session.tenant_id, session.connected_at.isoformat(), session.last_seen_at.isoformat()),
            )
            db.commit()
            return session

    def heartbeat(self, *, session_id: str, subject_id: str, tenant_id: str, now: datetime | None = None) -> DeviceSession:
        subject, tenant = self._scope(subject_id, tenant_id)
        session_id = str(session_id).strip()
        timestamp = self._utc(now)
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT session_id, device_id, device_name, subject_id, tenant_id, connected_at, last_seen_at, connected "
                "FROM device_sessions WHERE session_id=? AND subject_id=? AND tenant_id=?",
                (session_id, subject, tenant),
            ).fetchone()
            if row is None:
                raise ValueError("session not found")
            if not row[7]:
                raise ValueError("session is disconnected")
            db.execute("UPDATE device_sessions SET last_seen_at=? WHERE session_id=?", (timestamp.isoformat(), session_id))
            db.commit()
            return self._from_row((row[0], row[1], row[2], row[3], row[4], row[5], timestamp.isoformat(), 1))

    def disconnect(self, *, session_id: str, subject_id: str, tenant_id: str, now: datetime | None = None) -> DeviceSession:
        subject, tenant = self._scope(subject_id, tenant_id)
        session_id = str(session_id).strip()
        timestamp = self._utc(now)
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT session_id, device_id, device_name, subject_id, tenant_id, connected_at, last_seen_at, connected "
                "FROM device_sessions WHERE session_id=? AND subject_id=? AND tenant_id=?",
                (session_id, subject, tenant),
            ).fetchone()
            if row is None:
                raise ValueError("session not found")
            db.execute("UPDATE device_sessions SET last_seen_at=?, connected=0 WHERE session_id=?", (timestamp.isoformat(), session_id))
            db.commit()
            return self._from_row((row[0], row[1], row[2], row[3], row[4], row[5], timestamp.isoformat(), 0))

    def active(self, *, subject_id: str, tenant_id: str) -> tuple[DeviceSession, ...]:
        subject, tenant = self._scope(subject_id, tenant_id)
        with self._lock, sqlite3.connect(self.database_path) as db:
            rows = db.execute(
                "SELECT session_id, device_id, device_name, subject_id, tenant_id, connected_at, last_seen_at, connected "
                "FROM device_sessions WHERE subject_id=? AND tenant_id=? AND connected=1 ORDER BY connected_at ASC",
                (subject, tenant),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def is_connected(self, *, session_id: str, subject_id: str, tenant_id: str) -> bool:
        subject, tenant = self._scope(subject_id, tenant_id)
        with self._lock, sqlite3.connect(self.database_path) as db:
            row = db.execute(
                "SELECT connected FROM device_sessions WHERE session_id=? AND subject_id=? AND tenant_id=?",
                (str(session_id).strip(), subject, tenant),
            ).fetchone()
        return bool(row and row[0])
