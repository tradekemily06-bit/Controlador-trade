from __future__ import annotations

from integration.standalone_runtime import StandaloneRuntime


def test_runtime_starts_opt_in_backup_scheduler_and_stops_it(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "runtime-test-owner")
    monkeypatch.setenv("CONTROLADOR_AUTOMATIC_BACKUP_ENABLED", "true")
    monkeypatch.setenv("CONTROLADOR_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("CONTROLADOR_BACKUP_INTERVAL_SECONDS", "3600")
    runtime = StandaloneRuntime(runtime_dir)
    try:
        assert runtime.backup_scheduler is not None
        status = runtime.backup_scheduler.status()
        assert status["enabled"] is True
        assert status["worker_running"] is True
        assert status["interval_seconds"] == 3600
        assert status["last_run_at"] is None
    finally:
        runtime.close()
    assert runtime.backup_scheduler.status()["worker_running"] is False


def test_runtime_refuses_automatic_backup_without_external_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "runtime-test-owner")
    monkeypatch.setenv("CONTROLADOR_AUTOMATIC_BACKUP_ENABLED", "true")
    monkeypatch.delenv("CONTROLADOR_BACKUP_DIR", raising=False)
    with __import__("pytest").raises(RuntimeError, match="CONTROLADOR_BACKUP_DIR"):
        StandaloneRuntime(tmp_path / "runtime")