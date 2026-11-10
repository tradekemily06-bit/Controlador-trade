from pathlib import Path


def test_wsgi_request_threads_are_drained_before_runtime_locks_are_released():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    server = source.split("class ThreadingWSGIServer", 1)[1].split("def run(", 1)[0]
    assert "daemon_threads = False" in server
    assert "block_on_close = True" in server
    run = source.split("def run(", 1)[1]
    assert run.index("server.serve_forever()") < run.index("timed_exit_worker.stop()")
    assert run.index("timed_exit_worker.stop()") < run.index("_RUNTIME_PROCESS_LOCK.release()")


def test_startup_failure_releases_runtime_locks_before_propagating():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    startup = source.split("try:\n    _RUNTIME_PROCESS_LOCK.acquire()", 1)[1].split(
        "# Latest read-only market snapshots", 1
    )[0]
    assert "except BaseException:" in startup
    assert "_RUNTIME_PROCESS_LOCK.release()" in startup
    assert startup.index("_RUNTIME_PROCESS_LOCK.release()") < startup.rindex("raise")
    assert "except Exception:" in startup


def test_run_releases_runtime_locks_when_timed_exit_worker_import_or_construction_fails():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    run = source.split("def run(", 1)[1]
    protected = run.split("finally:", 1)[0]
    cleanup = run.split("finally:", 1)[1]

    assert protected.index("_RUNTIME_PROCESS_LOCK.acquire()") < protected.index("try:")
    assert protected.index("try:") < protected.index("from execution.timed_exit_worker import TimedExitWorker")
    assert protected.index("TimedExitWorker(SERVICE, OPERATIONAL_RUNTIME)") < protected.index("timed_exit_worker.start()")
    assert "timed_exit_worker = None" in protected
    assert "if timed_exit_worker is not None:" in cleanup
    assert cleanup.index("timed_exit_worker.stop()") < cleanup.index("_RUNTIME_PROCESS_LOCK.release()")
