from __future__ import annotations

import pytest

from integration.standalone_runtime import _stop_workers_and_report_active


class _Worker:
    def __init__(self, *, stop_error=False, status_error=False, running=False):
        self.stop_error = stop_error
        self.status_error = status_error
        self.running = running
        self.stop_called = False

    def stop(self):
        self.stop_called = True
        if self.stop_error:
            raise RuntimeError("simulated stop failure")

    def status(self):
        if self.status_error:
            raise RuntimeError("simulated status failure")
        return {"running": self.running}


def test_shutdown_requests_stop_from_every_worker_even_if_one_stop_fails():
    broken = _Worker(stop_error=True)
    healthy = _Worker()
    still_running = _stop_workers_and_report_active(
        ((broken, "running"), (healthy, "running"))
    )
    assert broken.stop_called is True
    assert healthy.stop_called is True
    assert still_running == ["_Worker"]


def test_shutdown_treats_status_error_as_unknown_and_keeps_worker_active():
    unknown = _Worker(status_error=True)
    healthy = _Worker()
    still_running = _stop_workers_and_report_active(
        ((unknown, "running"), (healthy, "running"))
    )
    assert unknown.stop_called is True
    assert healthy.stop_called is True
    assert still_running == ["_Worker"]


def test_shutdown_does_not_report_worker_stopped_when_status_is_malformed():
    class MalformedStatusWorker(_Worker):
        def status(self):
            return None

    worker = MalformedStatusWorker()
    assert _stop_workers_and_report_active(((worker, "running"),)) == [
        "MalformedStatusWorker"
    ]



def test_runtime_evidence_store_location_must_be_covered_by_backup_directory(tmp_path):
    from integration.standalone_runtime import _validate_runtime_store_location

    class Store:
        def __init__(self, database_path):
            self.database_path = str(database_path)

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    expected = runtime_dir / "news-evidence.sqlite3"
    _validate_runtime_store_location(Store(expected), runtime_dir, "news-evidence.sqlite3")

    with pytest.raises(ValueError, match="backup coverage"):
        _validate_runtime_store_location(
            Store(tmp_path / "outside.sqlite3"), runtime_dir, "news-evidence.sqlite3"
        )

    with pytest.raises(ValueError, match="backup coverage"):
        _validate_runtime_store_location(
            Store(":memory:"), runtime_dir, "news-evidence.sqlite3"
        )


def test_non_sqlite_shared_store_is_not_forced_into_local_backup_path(tmp_path):
    from integration.standalone_runtime import _validate_runtime_store_location

    _validate_runtime_store_location(object(), tmp_path, "economic-calendar.sqlite3")



def test_runtime_store_location_rejects_symlink_even_when_target_is_inside_runtime(tmp_path):
    from integration.standalone_runtime import _validate_runtime_store_location

    class Store:
        def __init__(self, database_path):
            self.database_path = str(database_path)

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    target = runtime_dir / "real-news.sqlite3"
    target.touch()
    link = runtime_dir / "news-evidence.sqlite3"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    with pytest.raises(ValueError, match="must not be a symlink"):
        _validate_runtime_store_location(
            Store(link), runtime_dir, "news-evidence.sqlite3"
        )
