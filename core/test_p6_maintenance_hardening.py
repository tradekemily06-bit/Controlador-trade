from datetime import datetime, timedelta, timezone

import pytest

from core.ecosystem_maintenance import (
    MAX_MAINTENANCE_DURATION_MINUTES,
    MaintenanceManager,
)


def future():
    return datetime.now(timezone.utc) + timedelta(hours=2)


def test_maintenance_rejects_excessive_duration(tmp_path):
    manager = MaintenanceManager(tmp_path / "maintenance.json")
    with pytest.raises(ValueError):
        manager.schedule(
            maintenance_id="m1",
            title="Update",
            message="Safe update",
            starts_at=future(),
            duration_minutes=MAX_MAINTENANCE_DURATION_MINUTES + 1,
        )


def test_maintenance_rejects_boolean_duration(tmp_path):
    manager = MaintenanceManager(tmp_path / "maintenance.json")
    with pytest.raises(ValueError):
        manager.schedule(
            maintenance_id="m1",
            title="Update",
            message="Safe update",
            starts_at=future(),
            duration_minutes=True,
        )


def test_maintenance_rejects_symlinked_state_file(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    state = tmp_path / "maintenance.json"
    state.symlink_to(target)
    manager = MaintenanceManager(state)
    with pytest.raises(OSError):
        manager.schedule(
            maintenance_id="m1",
            title="Update",
            message="Safe update",
            starts_at=future(),
            duration_minutes=5,
        )


def test_maintenance_refuses_stale_temporary_file(tmp_path):
    state = tmp_path / "maintenance.json"
    temporary = tmp_path / ".maintenance.json.tmp"
    temporary.write_text("attacker", encoding="utf-8")
    manager = MaintenanceManager(state)
    with pytest.raises(RuntimeError):
        manager.schedule(
            maintenance_id="m1",
            title="Update",
            message="Safe update",
            starts_at=future(),
            duration_minutes=5,
        )
    assert not state.exists()
