"""Multi-device connection policy for the trading ecosystem.

The ecosystem connection belongs to the trusted account/session, not to a
single screen. Opening the panel on another device therefore must not log the
existing device out. A connection is ended only by an explicit disconnect,
revocation, or a fail-closed security action.

This module is deliberately policy/state only. It does not execute orders and
it does not store credentials or session secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class DeviceConnection:
    connection_id: str
    subject_id: str
    tenant_id: str
    device_id: str
    state: ConnectionState
    connected_at: datetime
    last_seen_at: datetime
    disconnected_at: datetime | None = None
    disconnect_reason: str | None = None


class MultiDeviceConnectionPolicy:
    """Authoritative product rules for account connections across devices."""

    def connect(
        self,
        *,
        connection_id: str,
        subject_id: str,
        tenant_id: str,
        device_id: str,
        now: datetime | None = None,
    ) -> DeviceConnection:
        values = (connection_id, subject_id, tenant_id, device_id)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("connection identity values are required")
        event_time = self._utc(now)
        return DeviceConnection(
            connection_id=connection_id.strip(),
            subject_id=subject_id.strip(),
            tenant_id=tenant_id.strip(),
            device_id=device_id.strip(),
            state=ConnectionState.CONNECTED,
            connected_at=event_time,
            last_seen_at=event_time,
        )

    def heartbeat(self, connection: DeviceConnection, *, now: datetime | None = None) -> DeviceConnection:
        self._validate_connection(connection)
        if connection.state is not ConnectionState.CONNECTED:
            raise ValueError("only connected sessions can heartbeat")
        event_time = self._utc(now)
        if event_time < connection.last_seen_at:
            raise ValueError("heartbeat time cannot move backwards")
        return DeviceConnection(**{**connection.__dict__, "last_seen_at": event_time})

    def disconnect(
        self,
        connection: DeviceConnection,
        *,
        reason: str = "explicit user disconnect",
        now: datetime | None = None,
    ) -> DeviceConnection:
        self._validate_connection(connection)
        if connection.state is ConnectionState.REVOKED:
            return connection
        event_time = self._utc(now)
        if event_time < connection.last_seen_at:
            raise ValueError("disconnect time cannot move backwards")
        return DeviceConnection(
            **{
                **connection.__dict__,
                "state": ConnectionState.DISCONNECTED,
                "last_seen_at": event_time,
                "disconnected_at": event_time,
                "disconnect_reason": str(reason).strip() or "explicit user disconnect",
            }
        )

    def revoke(
        self,
        connection: DeviceConnection,
        *,
        reason: str = "security revocation",
        now: datetime | None = None,
    ) -> DeviceConnection:
        self._validate_connection(connection)
        event_time = self._utc(now)
        if event_time < connection.last_seen_at:
            raise ValueError("revocation time cannot move backwards")
        return DeviceConnection(
            **{
                **connection.__dict__,
                "state": ConnectionState.REVOKED,
                "last_seen_at": event_time,
                "disconnected_at": event_time,
                "disconnect_reason": str(reason).strip() or "security revocation",
            }
        )

    @staticmethod
    def same_account(left: DeviceConnection, right: DeviceConnection) -> bool:
        MultiDeviceConnectionPolicy._validate_connection(left)
        MultiDeviceConnectionPolicy._validate_connection(right)
        return left.subject_id == right.subject_id and left.tenant_id == right.tenant_id

    @staticmethod
    def can_operate(connection: DeviceConnection) -> bool:
        """Connection state alone never grants trading authority."""
        MultiDeviceConnectionPolicy._validate_connection(connection)
        return False

    @staticmethod
    def _validate_connection(connection: DeviceConnection) -> None:
        if not isinstance(connection, DeviceConnection):
            raise ValueError("invalid device connection")
        if not connection.connection_id.strip() or not connection.subject_id.strip() or not connection.tenant_id.strip() or not connection.device_id.strip():
            raise ValueError("connection identity values are required")

    @staticmethod
    def _utc(value: datetime | None) -> datetime:
        result = value or datetime.now(timezone.utc)
        if result.tzinfo is None:
            raise ValueError("connection timestamps must be timezone-aware")
        return result.astimezone(timezone.utc)
