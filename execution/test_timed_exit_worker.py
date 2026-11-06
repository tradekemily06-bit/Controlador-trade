from __future__ import annotations

import pytest

from execution.timed_exit_worker import TimedExitWorker


class _StillRunningThread:
    def __init__(self):
        self.alive = True
        self.join_timeout = None

    def join(self, timeout=None):
        self.join_timeout = timeout

    def is_alive(self):
        return self.alive


def test_stop_does_not_report_completion_while_worker_is_still_running():
    worker = TimedExitWorker(service=object(), operational_runtime=object())
    thread = _StillRunningThread()
    worker._thread = thread

    with pytest.raises(RuntimeError, match="ainda está ativo"):
        worker.stop(timeout=0.01)

    assert worker._stop.is_set()
    assert thread.join_timeout == 0.01
    assert worker._thread is thread


def test_stop_clears_worker_reference_only_after_thread_has_stopped():
    worker = TimedExitWorker(service=object(), operational_runtime=object())
    thread = _StillRunningThread()
    worker._thread = thread
    thread.alive = False

    worker.stop(timeout=0.01)

    assert worker._stop.is_set()
    assert worker._thread is None


def test_start_failure_clears_unstarted_thread_and_allows_safe_stop(monkeypatch):
    class _StartFailureThread:
        def __init__(self, *args, **kwargs):
            self.start_called = False

        def start(self):
            self.start_called = True
            raise RuntimeError("thread start failed")

    monkeypatch.setattr("execution.timed_exit_worker.Thread", _StartFailureThread)
    worker = TimedExitWorker(service=object(), operational_runtime=object())

    with pytest.raises(RuntimeError, match="thread start failed"):
        worker.start()

    assert worker._thread is None
    assert worker._stop.is_set()
    worker.stop()
    assert worker._thread is None
