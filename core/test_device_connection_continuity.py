from datetime import datetime, timezone

from core.device_connection_continuity import ConnectionState, DeviceConnectionContinuity


def test_connecting_phone_does_not_disconnect_computer():
    manager = DeviceConnectionContinuity()
    first = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    second = datetime(2026, 9, 15, 10, 1, tzinfo=timezone.utc)

    manager.connect(subject_id="user", tenant_id="tenant", device_id="computer", now=first)
    manager.connect(subject_id="user", tenant_id="tenant", device_id="phone", now=second)

    connected = {item.device_id for item in manager.list_connected(subject_id="user", tenant_id="tenant")}
    assert connected == {"computer", "phone"}
    assert manager.is_connected(subject_id="user", tenant_id="tenant", device_id="computer")
    assert manager.is_connected(subject_id="user", tenant_id="tenant", device_id="phone")


def test_disconnect_is_explicit_and_does_not_disconnect_other_device():
    manager = DeviceConnectionContinuity()
    now = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    manager.connect(subject_id="user", tenant_id="tenant", device_id="computer", now=now)
    manager.connect(subject_id="user", tenant_id="tenant", device_id="phone", now=now)

    disconnected = manager.disconnect(subject_id="user", tenant_id="tenant", device_id="phone", now=now)

    assert disconnected.state is ConnectionState.DISCONNECTED
    assert not manager.is_connected(subject_id="user", tenant_id="tenant", device_id="phone")
    assert manager.is_connected(subject_id="user", tenant_id="tenant", device_id="computer")


def test_revoke_all_is_available_for_security_incident_or_account_recovery():
    manager = DeviceConnectionContinuity()
    now = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    manager.connect(subject_id="user", tenant_id="tenant", device_id="computer", now=now)
    manager.connect(subject_id="user", tenant_id="tenant", device_id="phone", now=now)

    revoked = manager.revoke_all(subject_id="user", tenant_id="tenant", now=now)

    assert {item.device_id for item in revoked} == {"computer", "phone"}
    assert manager.list_connected(subject_id="user", tenant_id="tenant") == ()
