"""Safe maintenance lifecycle for planned ecosystem updates.

This module does not perform deployment. It gives the ecosystem a durable
contract for announcing a maintenance window before it starts, showing the
expected return time, and keeping the service explicitly unavailable while a
planned maintenance window is active.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import RLock


class MaintenanceStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class MaintenanceWindow:
    maintenance_id: str
    title: str
    message: str
    starts_at: datetime
    ends_at: datetime
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED

    @property
    def duration_seconds(self) -> int:
        return max(0, int((self.ends_at - self.starts_at).total_seconds()))

    def normalized(self, now: datetime | None = None) -> "MaintenanceWindow":
        current = _utc(now or datetime.now(timezone.utc))
        if self.status in {MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED}:
            return self
        if current >= self.ends_at:
            return MaintenanceWindow(**{**self.__dict__, "status": MaintenanceStatus.COMPLETED})
        if current >= self.starts_at:
            return MaintenanceWindow(**{**self.__dict__, "status": MaintenanceStatus.ACTIVE})
        return MaintenanceWindow(**{**self.__dict__, "status": MaintenanceStatus.SCHEDULED})

    def user_notice(self, now: datetime | None = None) -> dict[str, object]:
        state = self.normalized(now)
        blocked = state.status is MaintenanceStatus.ACTIVE
        return {
            "maintenance_id": state.maintenance_id,
            "title": state.title,
            "message": state.message,
            "status": state.status.value,
            "starts_at": state.starts_at.isoformat(),
            "ends_at": state.ends_at.isoformat(),
            "expected_return_at": state.ends_at.isoformat(),
            "duration_seconds": state.duration_seconds,
            "duration_minutes": max(1, (state.duration_seconds + 59) // 60),
            "trading_available": not blocked,
            "execution_blocked": blocked,
            "user_action": "aguardar" if blocked else "normal",
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("maintenance timestamps must include timezone")
    return value.astimezone(timezone.utc)


class MaintenanceManager:
    """Tracks one planned maintenance window and optionally persists it."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self._current: MaintenanceWindow | None = None
        self._state_path = Path(state_path) if state_path is not None else None
        self._lock = RLock()
        self._load()

    def _load(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._current = MaintenanceWindow(
                maintenance_id=str(payload["maintenance_id"]),
                title=str(payload["title"]),
                message=str(payload["message"]),
                starts_at=datetime.fromisoformat(str(payload["starts_at"])),
                ends_at=datetime.fromisoformat(str(payload["ends_at"])),
                status=MaintenanceStatus(str(payload["status"])),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # A corrupt maintenance state must fail closed at the execution
            # boundary rather than silently inventing an available state.
            self._current = None

    def _save(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        if self._current is None:
            payload = {"current": None}
        else:
            payload = {
                "maintenance_id": self._current.maintenance_id,
                "title": self._current.title,
                "message": self._current.message,
                "starts_at": self._current.starts_at.isoformat(),
                "ends_at": self._current.ends_at.isoformat(),
                "status": self._current.status.value,
            }
        temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        with temporary.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._state_path)

    def schedule(
        self,
        *,
        maintenance_id: str,
        title: str,
        message: str,
        starts_at: datetime,
        duration_minutes: int,
        now: datetime | None = None,
    ) -> MaintenanceWindow:
        with self._lock:
            if not maintenance_id.strip() or not title.strip() or not message.strip():
                raise ValueError("maintenance identity, title and message are required")
            start = _utc(starts_at)
            if duration_minutes < 1:
                raise ValueError("duration_minutes must be greater than zero")
            current = _utc(now or datetime.now(timezone.utc))
            if start <= current:
                raise ValueError("maintenance must be scheduled before it starts")
            if self._current is not None:
                current_state = self._current.normalized(current)
                if current_state.status in {MaintenanceStatus.SCHEDULED, MaintenanceStatus.ACTIVE}:
                    raise ValueError("an active or scheduled maintenance window already exists")
            end = start + timedelta(minutes=duration_minutes)
            self._current = MaintenanceWindow(maintenance_id.strip(), title.strip(), message.strip(), start, end)
            self._save()
            return self._current

    def begin(self, maintenance_id: str, *, now: datetime | None = None) -> MaintenanceWindow:
        with self._lock:
            if self._current is None or self._current.maintenance_id != maintenance_id:
                raise ValueError("maintenance window not found")
            current = self._current.normalized(now)
            if current.status is not MaintenanceStatus.ACTIVE:
                raise ValueError("maintenance is not active")
            self._current = current
            self._save()
            return current

    def cancel(self, maintenance_id: str) -> MaintenanceWindow:
        with self._lock:
            if self._current is None or self._current.maintenance_id != maintenance_id:
                raise ValueError("maintenance window not found")
            current = self._current.normalized()
            if current.status is not MaintenanceStatus.SCHEDULED:
                raise ValueError("only scheduled maintenance can be cancelled")
            self._current = MaintenanceWindow(**{**current.__dict__, "status": MaintenanceStatus.CANCELLED})
            self._save()
            return self._current

    def status(self, *, now: datetime | None = None) -> dict[str, object]:
        with self._lock:
            if self._current is None:
                return {"status": "NONE", "trading_available": True, "execution_blocked": False, "maintenance": None}
            current = self._current.normalized(now)
            if current != self._current:
                self._current = current
                self._save()
            blocked = current.status is MaintenanceStatus.ACTIVE
            return {
                "status": current.status.value,
                "trading_available": not blocked,
                "execution_blocked": blocked,
                "maintenance": current.user_notice(now),
            }

    def execution_blocked(self, *, now: datetime | None = None) -> bool:
        """Return whether the execution boundary must refuse new operations."""
        return self.status(now=now)["execution_blocked"] is True
