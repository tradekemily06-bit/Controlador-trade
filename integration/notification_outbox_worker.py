from __future__ import annotations

import threading
from typing import Any

from core.notification_outbox import PersistentNotificationOutbox, NotificationSink, redact_delivery_error


class NotificationOutboxWorker:
    """Lifecycle-managed dispatcher for a persistent notification outbox.

    The worker is intentionally transport-neutral. It starts only when the
    application injects a configured sink; it never creates credentials,
    subscriptions, or network destinations on its own.
    """

    def __init__(
        self,
        outbox: PersistentNotificationOutbox,
        sink: NotificationSink,
        *,
        poll_interval_seconds: float = 2.0,
        batch_size: int = 50,
    ) -> None:
        if outbox is None:
            raise ValueError("outbox is required")
        if not callable(getattr(sink, "deliver", None)):
            raise ValueError("sink must implement deliver(idempotency_key, payload)")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.outbox = outbox
        self.sink = sink
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.batch_size = batch_size
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_result: dict[str, int] | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="notification-outbox-worker",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.outbox.dispatch_due(self.sink, limit=self.batch_size)
                self._last_result = {
                    "claimed": result.claimed,
                    "delivered": result.delivered,
                    "retried": result.retried,
                    "dead_lettered": result.dead_lettered,
                }
                self._last_error = None
            except Exception as exc:
                self._last_error = redact_delivery_error(exc)
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
            "last_error": self._last_error,
            "last_result": dict(self._last_result) if self._last_result is not None else None,
            "outbox": self.outbox.status_counts(),
        }
