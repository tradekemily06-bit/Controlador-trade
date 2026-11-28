"""Process-lifetime RSS news polling and owner-scoped evidence ingestion."""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


class NewsPollingWorker:
    """Poll a configured RSS provider and persist evidence through a trusted correlator.

    The worker never fetches article bodies or confirms facts. It only stores
    provider-returned headline evidence; source policies and owner-scoped
    persistence are configured by the host.
    """

    def __init__(
        self,
        provider: Any,
        evidence_correlator: Any,
        *,
        interval_seconds: float = 60.0,
        limit: int = 50,
    ) -> None:
        if not callable(getattr(provider, "latest", None)) or not callable(
            getattr(provider, "status", None)
        ):
            raise TypeError("news provider must implement latest and status")
        if not callable(getattr(evidence_correlator, "ingest", None)):
            raise TypeError("trusted news evidence correlator is required")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(float(interval_seconds))
            or interval_seconds < 30
            or interval_seconds > 3600
        ):
            raise ValueError("news polling interval must be between 30 and 3600 seconds")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("news polling limit must be between 1 and 50")
        self.provider = provider
        self.evidence_correlator = evidence_correlator
        self.interval_seconds = float(interval_seconds)
        self.limit = limit
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_poll_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error_class: str | None = None
        self._last_state = "NOT_RUN"
        self._last_item_count = 0
        self._last_processed = 0
        self._last_errors = 0

    def run_once(self) -> dict[str, Any]:
        try:
            items = self.provider.latest(limit=self.limit)
            provider_status = self.provider.status()
            if not isinstance(items, (list, tuple)):
                raise ValueError("news provider returned an invalid collection")
            if not isinstance(provider_status, dict):
                raise ValueError("news provider returned invalid status")
        except Exception as exc:
            with self._lock:
                self._last_poll_at = datetime.now(timezone.utc).isoformat()
                self._last_state = "POLL_FAILED"
                self._last_error_class = type(exc).__name__
                self._last_item_count = 0
                self._last_processed = 0
                self._last_errors = 1
                return self.status()

        processed = 0
        errors = 0
        ingested_at = datetime.now(timezone.utc)
        for item in items:
            article_url = getattr(item, "url", None)
            host = urlparse(article_url).hostname.lower().rstrip(".") if isinstance(article_url, str) else ""
            if not host:
                errors += 1
                continue
            try:
                self.evidence_correlator.ingest(
                    item,
                    source_id=host,
                    ingested_at=ingested_at,
                )
                processed += 1
            except Exception:
                errors += 1

        configured = bool(provider_status.get("configured", False))
        live = bool(provider_status.get("live", False))
        if not configured:
            state = "NOT_CONFIGURED"
        elif not live:
            state = "SOURCE_UNAVAILABLE"
        elif errors:
            state = "PARTIAL"
        else:
            state = "POLL_SUCCEEDED"

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._last_poll_at = now
            if live:
                self._last_success_at = now
            self._last_state = state
            self._last_error_class = None
            self._last_item_count = len(items)
            self._last_processed = processed
            self._last_errors = errors
            return self.status()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="controlador-news-evidence-poller",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                with self._lock:
                    self._last_state = "POLL_FAILED"
                    self._last_error_class = type(exc).__name__
            self._stop.wait(self.interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
            if not thread.is_alive():
                self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "configured": True,
                "worker_running": bool(self._thread is not None and self._thread.is_alive()),
                "interval_seconds": self.interval_seconds,
                "limit": self.limit,
                "last_poll_at": self._last_poll_at,
                "last_success_at": self._last_success_at,
                "last_state": self._last_state,
                "last_error_class": self._last_error_class,
                "last_item_count": self._last_item_count,
                "last_processed": self._last_processed,
                "last_errors": self._last_errors,
                "fact_confirmation": "NEVER_AUTOMATIC",
                "execution_authorized": False,
            }
