from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True)
class DeviceConnection:
    device_id: str
    subject_id: str
    tenant_id: str
    state: ConnectionState
    connected_at: datetime
    last_seen_at: datetime


class DeviceConnectionContinuity:
    """Keeps account connection intent independent from the device in use.

    A phone and a computer are separate device sessions under the same trusted
    account scope. Connecting one does not disconnect the other. A session is
    disconnected only by an explicit disconnect/revoke action or by a higher
    security boundary (for example account/session revocation).

    This layer stores connection intent only; it never stores passwords or API
    credentials and it never grants trading authority by itself.
    """

    def __init__(self) -> None:
        self._connections: dict[tuple[str, str, str], DeviceConnection] = {}

    @staticmethod
    def _scope(subject_id: str, tenant_id: str, device_id: str) -> tuple[str, str, str]:
        values = (subject_id, tenant_id, device_id)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("subject_id, tenant_id e device_id são obrigatórios")
        return tuple(value.strip() for value in values)  # type: ignore[return-value]

    def connect(
        self,
        *,
        subject_id: str,
        tenant_id: str,
        device_id: str,
        now: datetime | None = None,
    ) -> DeviceConnection:
        key = self._scope(subject_id, tenant_id, device_id)
        event_time = now or datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            raise ValueError("now deve ser timezone-aware")
        existing = self._connections.get(key)
        connected_at = existing.connected_at if existing else event_time
        connection = DeviceConnection(key[2], key[0], key[1], ConnectionState.CONNECTED, connected_at, event_time)
        self._connections[key] = connection
        return connection

    def heartbeat(
        self,
        *,
        subject_id: str,
        tenant_id: str,
        device_id: str,
        now: datetime | None = None,
    ) -> DeviceConnection:
        key = self._scope(subject_id, tenant_id, device_id)
        current = self._connections.get(key)
        if current is None or current.state is ConnectionState.DISCONNECTED:
            raise ValueError("device session is not connected")
        event_time = now or datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            raise ValueError("now deve ser timezone-aware")
        updated = DeviceConnection(current.device_id, current.subject_id, current.tenant_id, current.state, current.connected_at, event_time)
        self._connections[key] = updated
        return updated

    def disconnect(self, *, subject_id: str, tenant_id: str, device_id: str, now: datetime | None = None) -> DeviceConnection:
        key = self._scope(subject_id, tenant_id, device_id)
        current = self._connections.get(key)
        if current is None:
            raise ValueError("device session não encontrada")
        event_time = now or datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            raise ValueError("now deve ser timezone-aware")
        updated = DeviceConnection(current.device_id, current.subject_id, current.tenant_id, ConnectionState.DISCONNECTED, current.connected_at, event_time)
        self._connections[key] = updated
        return updated

    def is_connected(self, *, subject_id: str, tenant_id: str, device_id: str) -> bool:
        key = self._scope(subject_id, tenant_id, device_id)
        current = self._connections.get(key)
        return current is not None and current.state is ConnectionState.CONNECTED

    def list_connected(self, *, subject_id: str, tenant_id: str) -> tuple[DeviceConnection, ...]:
        if not isinstance(subject_id, str) or not subject_id.strip() or not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("subject_id e tenant_id são obrigatórios")
        return tuple(
            item
            for item in self._connections.values()
            if item.subject_id == subject_id.strip()
            and item.tenant_id == tenant_id.strip()
            and item.state is ConnectionState.CONNECTED
        )

    def revoke_all(self, *, subject_id: str, tenant_id: str, now: datetime | None = None) -> tuple[DeviceConnection, ...]:
        connected = self.list_connected(subject_id=subject_id, tenant_id=tenant_id)
        event_time = now or datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            raise ValueError("now deve ser timezone-aware")
        revoked: list[DeviceConnection] = []
        for current in connected:
            revoked.append(self.disconnect(subject_id=subject_id, tenant_id=tenant_id, device_id=current.device_id, now=event_time))
        return tuple(revoked)


def new_device_id() -> str:
    return str(uuid4())
