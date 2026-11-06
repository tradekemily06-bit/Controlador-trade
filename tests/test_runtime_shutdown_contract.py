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
