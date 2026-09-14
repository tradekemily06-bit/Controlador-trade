from datetime import datetime, timezone

import pytest

from core.ecosystem_maintenance import MaintenanceManager, MaintenanceStatus


def test_maintenance_requires_future_start_and_exposes_return_time():
    manager = MaintenanceManager()
    now = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    window = manager.schedule(
        maintenance_id="maint-1",
        title="Atualização programada",
        message="O ecossistema ficará temporariamente indisponível.",
        starts_at=datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc),
        duration_minutes=30,
        now=now,
    )

    notice = window.user_notice(now)
    assert notice["status"] == MaintenanceStatus.SCHEDULED.value
    assert notice["expected_return_at"] == "2026-09-14T21:30:00+00:00"
    assert notice["duration_minutes"] == 30
    assert notice["trading_available"] is False


def test_maintenance_becomes_active_then_completed():
    manager = MaintenanceManager()
    start = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)
    manager.schedule(maintenance_id="maint-2", title="Update", message="Aviso", starts_at=start, duration_minutes=10, now=datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc))

    assert manager.status(now=start)["status"] == MaintenanceStatus.ACTIVE.value
    assert manager.status(now=datetime(2026, 9, 14, 21, 11, tzinfo=timezone.utc))["status"] == MaintenanceStatus.COMPLETED.value
    assert manager.status(now=datetime(2026, 9, 14, 21, 11, tzinfo=timezone.utc))["trading_available"] is True


def test_maintenance_cannot_be_scheduled_in_the_past():
    with pytest.raises(ValueError):
        MaintenanceManager().schedule(
            maintenance_id="maint-3",
            title="Update",
            message="Aviso",
            starts_at=datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc),
            duration_minutes=10,
            now=datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc),
        )
