"""Opt-in periodic backups for a long-running standalone runtime.

The scheduler only runs while the application process is alive. It does not
claim off-host replication or deployment-level availability.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class SQLiteBackupScheduler:
    def __init__(self, backup_service, *, additional_backup_services=(), interval_seconds: int = 86400) -> None:
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
            raise ValueError("interval_seconds must be an integer")
        if interval_seconds < 3600:
            raise ValueError("automatic backup interval must be at least one hour")
        self.backup_service = backup_service
        self.additional_backup_services = tuple(additional_backup_services)
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_run_at: str | None = None
        self._last_status = "WAITING_FOR_FIRST_SCHEDULE"
        self._last_result: dict[str, Any] | None = None

    def _run_backup(self) -> None:
        started = datetime.now(timezone.utc).isoformat()
        try:
            primary = self.backup_service.backup()
            components = {"runtime_databases": primary}
            components.update({
                f"additional_{index + 1}": service.backup()
                for index, service in enumerate(self.additional_backup_services)
            })
            statuses = [
                item.get("status")
                for component in components.values()
                for item in component.get("results", [])
            ]
            component_failures = any(
                component.get("status") in {"SOURCE_UNSAFE", "PARTIAL_OR_FAILED", "FAILED"}
                for component in components.values()
            )
            succeeded = (
                bool(statuses)
                and all(status == "BACKUP_CREATED" for status in statuses)
                and not component_failures
            )
            state = "SUCCESS" if succeeded else "PARTIAL_OR_FAILED"
            result = {
                "provider": "COMPOSITE_LOCAL_SQLITE_BACKUP",
                "components": components,
                "results": [
                    item for component in components.values()
                    for item in component.get("results", [])
                ],
                "execution_authorized": False,
            }
        except Exception as exc:  # keep the long-running scheduler alive
            result = {"status": "BACKUP_FAILED", "error_class": type(exc).__name__}
            state = "FAILED"
        with self._lock:
            self._last_run_at = started
            self._last_status = state
            self._last_result = result

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._run_backup()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="controlador-sqlite-backup", daemon=True
            )
            self._thread.start()

    def run_once(self) -> dict[str, Any]:
        self._run_backup()
        return self.status()

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=None if timeout is None else max(0.0, timeout))
        with self._lock:
            if thread is None or not thread.is_alive():
                self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            return {
                "provider": "LOCAL_SQLITE_SCHEDULED",
                "enabled": True,
                "worker_running": bool(thread is not None and thread.is_alive()),
                "interval_seconds": self.interval_seconds,
                "last_run_at": self._last_run_at,
                "last_status": self._last_status,
                "last_result": self._last_result,
                "off_host_replication": "NOT_CONFIGURED",
                "deployment_continuity": "PROCESS_LIFETIME_ONLY",
                "execution_authorized": False,
            }
