"""Safe maintenance lifecycle for planned ecosystem updates.

This module does not perform deployment. It gives the ecosystem a durable
contract for announcing a maintenance window before it starts, showing the
expected return time, and keeping the service explicitly unavailable while a
planned maintenance window is active.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


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
            "trading_available": False,
            "user_action": "aguardar" if state.status in {MaintenanceStatus.SCHEDULED, MaintenanceStatus.ACTIVE} else "normal",
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("maintenance timestamps must include timezone")
    return value.astimezone(timezone.utc)


class MaintenanceManager:
    """Tracks the current planned maintenance window."""

    def __init__(self) -> None:
        self._current: MaintenanceWindow | None = None

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
        if not maintenance_id.strip() or not title.strip() or not message.strip():
            raise ValueError("maintenance identity, title and message are required")
        start = _utc(starts_at)
        if duration_minutes < 1:
            raise ValueError("duration_minutes must be greater than zero")
        current = _utc(now or datetime.now(timezone.utc))
        if start <= current:
            raise ValueError("maintenance must be scheduled before it starts")
        end = start + timedelta(minutes=duration_minutes)
        self._current = MaintenanceWindow(maintenance_id.strip(), title.strip(), message.strip(), start, end)
        return self._current

    def begin(self, maintenance_id: str, *, now: datetime | None = None) -> MaintenanceWindow:
        if self._current is None or self._current.maintenance_id != maintenance_id:
            raise ValueError("maintenance window not found")
        current = self._current.normalized(now)
        if current.status is not MaintenanceStatus.ACTIVE:
            raise ValueError("maintenance is not active")
        self._current = current
        return current

    def cancel(self, maintenance_id: str) -> MaintenanceWindow:
        if self._current is None or self._current.maintenance_id != maintenance_id:
            raise ValueError("maintenance window not found")
        self._current = MaintenanceWindow(**{**self._current.__dict__, "status": MaintenanceStatus.CANCELLED})
        return self._current

    def status(self, *, now: datetime | None = None) -> dict[str, object]:
        if self._current is None:
            return {"status": "NONE", "trading_available": True, "maintenance": None}
        current = self._current.normalized(now)
        self._current = current
        return {"status": current.status.value, "trading_available": False if current.status in {MaintenanceStatus.SCHEDULED, MaintenanceStatus.ACTIVE} else True, "maintenance": current.user_notice(now)}
