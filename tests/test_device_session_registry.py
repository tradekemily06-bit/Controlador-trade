from datetime import datetime, timezone

from core.device_session_registry import DeviceSessionRegistry


def test_two_devices_stay_connected_independently(tmp_path):
    registry = DeviceSessionRegistry(tmp_path / "sessions.sqlite3")
    now = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)

    phone = registry.connect(device_id="phone-1", device_name="Phone", subject_id="user-1", tenant_id="tenant-1", now=now)
    notebook = registry.connect(device_id="notebook-1", device_name="Notebook", subject_id="user-1", tenant_id="tenant-1", now=now)

    active = registry.active(subject_id="user-1", tenant_id="tenant-1")
    assert {item.session_id for item in active} == {phone.session_id, notebook.session_id}
    assert registry.is_connected(session_id=phone.session_id, subject_id="user-1", tenant_id="tenant-1")
    assert registry.is_connected(session_id=notebook.session_id, subject_id="user-1", tenant_id="tenant-1")


def test_disconnect_is_explicit_and_does_not_disconnect_other_device(tmp_path):
    registry = DeviceSessionRegistry(tmp_path / "sessions.sqlite3")
    phone = registry.connect(device_id="phone-1", device_name="Phone", subject_id="user-1", tenant_id="tenant-1")
    notebook = registry.connect(device_id="notebook-1", device_name="Notebook", subject_id="user-1", tenant_id="tenant-1")

    registry.disconnect(session_id=phone.session_id, subject_id="user-1", tenant_id="tenant-1")

    assert not registry.is_connected(session_id=phone.session_id, subject_id="user-1", tenant_id="tenant-1")
    assert registry.is_connected(session_id=notebook.session_id, subject_id="user-1", tenant_id="tenant-1")
    assert len(registry.active(subject_id="user-1", tenant_id="tenant-1")) == 1


def test_reopen_same_device_reuses_existing_connection(tmp_path):
    registry = DeviceSessionRegistry(tmp_path / "sessions.sqlite3")
    first = registry.connect(device_id="phone-1", device_name="Phone", subject_id="user-1", tenant_id="tenant-1")
    second = registry.connect(device_id="phone-1", device_name="Phone renamed", subject_id="user-1", tenant_id="tenant-1")

    assert second.session_id == first.session_id
    assert second.connected is True
    assert second.device_name == "Phone renamed"


def test_state_survives_new_registry_instance(tmp_path):
    path = tmp_path / "sessions.sqlite3"
    first = DeviceSessionRegistry(path)
    session = first.connect(device_id="phone-1", device_name="Phone", subject_id="user-1", tenant_id="tenant-1")

    second = DeviceSessionRegistry(path)
    active = second.active(subject_id="user-1", tenant_id="tenant-1")
    assert [item.session_id for item in active] == [session.session_id]
