"""Bounded lifecycle manager for one OAuth refresh worker per trusted owner."""
from __future__ import annotations

import threading
from typing import Any

from security.tenant_context import TenantContext
from integration.tenant_oauth_refresh_worker import TenantOAuthRefreshWorker


class TenantOAuthRefreshWorkerManager:
    """Keep each tenant/subject refresh scan isolated and lifecycle-managed.

    Owners are registered only by trusted internal code (runtime identity or
    the OAuth state vault callback), never from arbitrary request payloads.
    The in-memory registry is intentionally bounded and must be repopulated
    after process restart by authenticated activity or OAuth completion.
    """

    def __init__(
        self,
        token_vault: Any,
        oauth_service: Any,
        *,
        max_owners: int = 100,
        poll_interval_seconds: float = 60.0,
        refresh_within_seconds: int = 900,
    ) -> None:
        if isinstance(max_owners, bool) or not isinstance(max_owners, int) or not 1 <= max_owners <= 10000:
            raise ValueError("max_owners must be between 1 and 10000")
        self.token_vault = token_vault
        self.oauth_service = oauth_service
        self.max_owners = max_owners
        self.poll_interval_seconds = poll_interval_seconds
        self.refresh_within_seconds = refresh_within_seconds
        self._workers: dict[str, TenantOAuthRefreshWorker] = {}
        self._owners: dict[str, TenantContext] = {}
        self._lock = threading.RLock()

    def register_owner(self, owner: TenantContext) -> bool:
        if not isinstance(owner, TenantContext):
            raise ValueError("trusted tenant context is required")
        with self._lock:
            key = owner.key
            existing = self._workers.get(key)
            if existing is not None:
                return False
            if len(self._workers) >= self.max_owners:
                raise RuntimeError("OAuth refresh worker owner capacity reached")
            worker = TenantOAuthRefreshWorker(
                self.token_vault,
                self.oauth_service,
                owner,
                poll_interval_seconds=self.poll_interval_seconds,
                refresh_within_seconds=self.refresh_within_seconds,
            )
            self._owners[key] = owner
            self._workers[key] = worker
            worker.start()
            return True

    def unregister_owner(self, owner: TenantContext) -> bool:
        if not isinstance(owner, TenantContext):
            raise ValueError("trusted tenant context is required")
        with self._lock:
            worker = self._workers.pop(owner.key, None)
            self._owners.pop(owner.key, None)
        if worker is None:
            return False
        worker.stop()
        if worker.status()["running"]:
            with self._lock:
                self._workers[owner.key] = worker
                self._owners[owner.key] = owner
            raise RuntimeError("OAuth refresh worker did not stop")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            worker.stop(timeout=timeout)
        still_running = [worker for worker in workers if worker.status()["running"]]
        if still_running:
            raise RuntimeError("one or more tenant OAuth refresh workers remain active")
        with self._lock:
            self._workers.clear()
            self._owners.clear()

    def owner_status(self, owner: TenantContext) -> dict[str, Any]:
        """Return refresh-worker health only for the exact trusted owner."""
        if not isinstance(owner, TenantContext):
            raise ValueError("trusted tenant context is required")
        with self._lock:
            worker = self._workers.get(owner.key)
        if worker is None:
            return {
                "configured": self.oauth_service is not None,
                "registered": False,
                "running": False,
                "state": "OWNER_NOT_REGISTERED",
                "execution_authorized": False,
            }
        status = worker.status()
        return {
            "configured": status["configured"],
            "registered": True,
            "running": status["running"],
            "last_scan_at": status["last_scan_at"],
            "last_error": status["last_error"],
            "last_result": status["last_result"],
            "refresh_within_seconds": status["refresh_within_seconds"],
            "state": "RUNNING" if status["running"] and status["last_error"] is None else (
                "DEGRADED" if status["last_error"] else "STOPPED"
            ),
            "execution_authorized": False,
        }

    @property
    def running(self) -> bool:
        with self._lock:
            return any(worker.status()["running"] for worker in self._workers.values())

    def status(self) -> dict[str, Any]:
        with self._lock:
            workers = list(self._workers.values())
        states = [worker.status() for worker in workers]
        return {
            "configured": True,
            "running": any(item["running"] for item in states),
            "registered_owner_count": len(states),
            "running_owner_count": sum(1 for item in states if item["running"]),
            "failed_scan_count": sum(1 for item in states if item["last_error"]),
            "execution_authorized": False,
        }
