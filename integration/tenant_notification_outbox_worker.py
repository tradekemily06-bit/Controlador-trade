from __future__ import annotations

import threading
import time
from typing import Any

from core.tenant_notification_outbox import TenantNotificationOutbox, TenantNotificationSink


class TenantNotificationOutboxWorker:
    """Background delivery worker for explicitly tenant-addressed events."""

    def __init__(self, outbox: TenantNotificationOutbox, sink: TenantNotificationSink,
                 *, poll_interval_seconds: float = 2.0, batch_size: int = 50) -> None:
        if outbox is None or not callable(getattr(sink, "deliver", None)):
            raise ValueError("tenant outbox and tenant-aware sink are required")
        if poll_interval_seconds <= 0 or isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("invalid worker polling configuration")
        self.outbox = outbox
        self.sink = sink
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.batch_size = batch_size
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_result: dict[str, int] | None = None
        self._last_cycle_at: float | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="tenant-notification-outbox-worker", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.outbox.dispatch_due(self.sink, limit=self.batch_size)
                with self._lock:
                    self._last_result = {
                        "claimed": result.claimed, "delivered": result.delivered,
                        "retried": result.retried, "dead_lettered": result.dead_lettered,
                    }
                    self._last_error = None
                    self._last_cycle_at = time.time()
            except Exception as exc:
                with self._lock:
                    # Do not persist exception text: provider errors can contain secrets.
                    self._last_error = type(exc).__name__
                    self._last_cycle_at = time.time()
            self._stop.wait(self.poll_interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
            with self._lock:
                if self._thread is thread and not thread.is_alive():
                    self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            running = bool(thread is not None and thread.is_alive())
            last_error = self._last_error
            last_result = dict(self._last_result) if self._last_result is not None else None
            last_cycle_at = self._last_cycle_at
            stop_requested = self._stop.is_set()
        state = "STOPPING" if stop_requested and running else "DEGRADED" if running and last_error else "RUNNING" if running else "STOPPED"
        return {
            "configured": True, "running": running, "state": state,
            "stop_requested": stop_requested, "last_error": last_error,
            "last_result": last_result, "last_cycle_at": last_cycle_at,
            "outbox": self.outbox.status_counts(),
        }
