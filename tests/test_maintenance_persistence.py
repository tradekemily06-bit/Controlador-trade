from datetime import datetime, timedelta, timezone

from core.ecosystem_maintenance import MaintenanceManager


def test_maintenance_survives_restart_and_blocks_during_active_window(tmp_path):
    state = tmp_path / "maintenance.json"
    start = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    manager = MaintenanceManager(state)
    manager.schedule(
        maintenance_id="m1",
        title="Update",
        message="Planned",
        starts_at=start,
        duration_minutes=30,
        now=start - timedelta(minutes=5),
    )

    restarted = MaintenanceManager(state)
    status = restarted.status(now=start + timedelta(minutes=1))
    assert status["status"] == "ACTIVE"
    assert status["trading_available"] is False
    assert status["execution_blocked"] is True


def test_corrupt_maintenance_state_fails_closed(tmp_path):
    state = tmp_path / "maintenance.json"
    state.write_text("not-json", encoding="utf-8")
    manager = MaintenanceManager(state)
    status = manager.status()
    assert status["status"] == "CORRUPT"
    assert status["trading_available"] is False
    assert status["execution_blocked"] is True
    assert status["recovery_required"] is True
