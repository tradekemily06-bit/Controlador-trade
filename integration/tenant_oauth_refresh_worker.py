"""Lifecycle-managed tenant OAuth token refresh worker.

Only refreshes credentials that the encrypted vault reports as approaching
expiry. The worker never exposes token material and delegates coordination to
the OAuth service's configured refresh guard.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from security.tenant_context import TenantContext


class TenantOAuthRefreshWorker:
    def __init__(
        self,
        token_vault: Any,
        oauth_service: Any,
        owner: TenantContext,
        *,
        poll_interval_seconds: float = 60.0,
        refresh_within_seconds: int = 900,
        batch_size: int = 50,
    ) -> None:
        if not callable(getattr(token_vault, "refresh_candidates", None)):
            raise ValueError("token vault must implement refresh_candidates")
        if not callable(getattr(oauth_service, "refresh", None)):
            raise ValueError("OAuth service must implement refresh")
        if not isinstance(owner, TenantContext):
            raise ValueError("trusted tenant context is required")
        if isinstance(poll_interval_seconds, bool) or not isinstance(poll_interval_seconds, (int, float)) or poll_interval_seconds < 5:
            raise ValueError("poll interval must be at least 5 seconds")
        if isinstance(refresh_within_seconds, bool) or not isinstance(refresh_within_seconds, int) or not 1 <= refresh_within_seconds <= 86400:
            raise ValueError("refresh window must be between 1 and 86400 seconds")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch size must be between 1 and 1000")
        self.token_vault = token_vault
        self.oauth_service = oauth_service
        self.owner = owner
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.refresh_within_seconds = refresh_within_seconds
        self.batch_size = batch_size
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_scan_at: str | None = None
        self._last_error: str | None = None
        self._last_result = {"candidates": 0, "refreshed": 0, "failed": 0}

    def run_once(self) -> dict[str, int]:
        candidates = self.token_vault.refresh_candidates(
            self.owner,
            within_seconds=self.refresh_within_seconds,
            limit=self.batch_size,
        )
        refreshed = failed = 0
        for candidate in candidates:
            if self._stop.is_set():
                break
            try:
                self.oauth_service.refresh(
                    self.owner, connection_id=candidate["connection_id"]
                )
                refreshed += 1
            except Exception:
                # Do not retain provider exception text: token endpoints and
                # proxies may include sensitive query values in error details.
                failed += 1
        result = {"candidates": len(candidates), "refreshed": refreshed, "failed": failed}
        self._last_result = result
        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        self._last_error = "one_or_more_refreshes_failed" if failed else None
        return dict(result)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="tenant-oauth-refresh-worker", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                self._last_error = "refresh_scan_failed"
            self._stop.wait(self.poll_interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
            if not thread.is_alive():
                self._thread = None

    def status(self) -> dict[str, Any]:
        thread = self._thread
        return {
            "configured": True,
            "running": bool(thread is not None and thread.is_alive()),
            "last_scan_at": self._last_scan_at,
            "last_error": self._last_error,
            "last_result": dict(self._last_result),
            "refresh_within_seconds": self.refresh_within_seconds,
            "execution_authorized": False,
        }
