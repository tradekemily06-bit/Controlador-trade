from __future__ import annotations

import threading
import time

import pytest

from core.sqlite_backup_scheduler import SQLiteBackupScheduler


class FakeBackupService:
    def __init__(self, result=None, error=None):
        self.result = result or {"results": [{"status": "BACKUP_CREATED"}]}
        self.error = error
        self.calls = 0
        self.called = threading.Event()

    def backup(self):
        self.calls += 1
        self.called.set()
        if self.error:
            raise self.error
        return self.result


def test_scheduler_requires_safe_minimum_interval():
    with pytest.raises(ValueError):
        SQLiteBackupScheduler(FakeBackupService(), interval_seconds=30)


def test_run_once_reports_success_and_does_not_claim_offsite_replication():
    service = FakeBackupService()
    scheduler = SQLiteBackupScheduler(service, interval_seconds=3600)
    status = scheduler.run_once()
    assert service.calls == 1
    assert status["last_status"] == "SUCCESS"
    assert status["last_run_at"]
    assert status["off_host_replication"] == "NOT_CONFIGURED"
    assert status["execution_authorized"] is False


def test_scheduler_survives_backup_exception():
    scheduler = SQLiteBackupScheduler(
        FakeBackupService(error=OSError("storage unavailable")),
        interval_seconds=3600,
    )
    status = scheduler.run_once()
    assert status["last_status"] == "FAILED"
    assert status["last_result"]["error_class"] == "OSError"


def test_scheduler_runs_on_interval_and_stops():
    service = FakeBackupService()
    scheduler = SQLiteBackupScheduler(service, interval_seconds=3600)
    # Keep the production minimum interval; shorten only the event wait in this test.
    scheduler.interval_seconds = 0.02
    scheduler.start()
    assert service.called.wait(0.5)
    scheduler.stop()
    assert service.calls >= 1
    assert scheduler.status()["worker_running"] is False
