from __future__ import annotations

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
