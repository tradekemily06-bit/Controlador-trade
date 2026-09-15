from datetime import datetime, timezone

import pytest

from core.multi_device_connection import ConnectionState, MultiDeviceConnectionPolicy


def test_switching_devices_does_not_disconnect_existing_connection():
    policy = MultiDeviceConnectionPolicy()
    t0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    first = policy.connect(connection_id="c1", subject_id="u1", tenant_id="t1", device_id="phone", now=t0)
    second = policy.connect(connection_id="c2", subject_id="u1", tenant_id="t1", device_id="laptop", now=t0)

    assert first.state is ConnectionState.CONNECTED
    assert second.state is ConnectionState.CONNECTED
    assert policy.same_account(first, second) is True


def test_connection_ends_only_by_explicit_disconnect_or_revoke():
    policy = MultiDeviceConnectionPolicy()
    t0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    connection = policy.connect(connection_id="c1", subject_id="u1", tenant_id="t1", device_id="phone", now=t0)
    heartbeat = policy.heartbeat(connection, now=datetime(2026, 9, 15, 10, 5, tzinfo=timezone.utc))
    assert heartbeat.state is ConnectionState.CONNECTED

    disconnected = policy.disconnect(heartbeat, now=datetime(2026, 9, 15, 10, 6, tzinfo=timezone.utc))
    assert disconnected.state is ConnectionState.DISCONNECTED
    assert disconnected.disconnected_at is not None

    revoked = policy.revoke(heartbeat, now=datetime(2026, 9, 15, 10, 7, tzinfo=timezone.utc))
    assert revoked.state is ConnectionState.REVOKED


def test_connection_never_grants_trading_authority():
    policy = MultiDeviceConnectionPolicy()
    connection = policy.connect(connection_id="c1", subject_id="u1", tenant_id="t1", device_id="phone")
    assert policy.can_operate(connection) is False


def test_naive_timestamps_are_rejected():
    policy = MultiDeviceConnectionPolicy()
    with pytest.raises(ValueError):
        policy.connect(connection_id="c1", subject_id="u1", tenant_id="t1", device_id="phone", now=datetime(2026, 9, 15, 10, 0))
