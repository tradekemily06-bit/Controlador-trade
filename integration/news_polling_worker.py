"""Process-lifetime RSS news polling and owner-scoped evidence ingestion."""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from analysis.news_event_intelligence import classify_market_news


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
        on_evidence=None,
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
        if on_evidence is not None and not callable(on_evidence):
            raise TypeError("on_evidence must be callable when provided")
        self.limit = limit
        self.on_evidence = on_evidence
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
        self._last_notification_errors = 0
        self._last_items: tuple[Any, ...] = ()

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

        configured = bool(provider_status.get("configured", False))
        live = bool(provider_status.get("live", False))
        try:
            feed_count = int(provider_status.get("feed_count", 1 if live else 0))
            successful_feeds = int(
                provider_status.get("successful_feeds", feed_count if live else 0)
            )
        except (TypeError, ValueError):
            feed_count = 0
            successful_feeds = 0
        feed_coverage_partial = (
            configured and live
            and (feed_count <= 0 or successful_feeds < feed_count)
        )
        if not configured or not live:
            with self._lock:
                self._last_poll_at = datetime.now(timezone.utc).isoformat()
                self._last_state = "NOT_CONFIGURED" if not configured else "SOURCE_UNAVAILABLE"
                self._last_error_class = None
                self._last_item_count = len(items)
                self._last_processed = 0
                self._last_errors = 0
                return self.status()

        with self._lock:
            self._last_items = tuple(items)

        processed = 0
        errors = 0
        notification_errors = 0
        ingested_at = datetime.now(timezone.utc)
        for item in items:
            article_url = getattr(item, "url", None)
            try:
                parsed_url = urlparse(article_url) if isinstance(article_url, str) else None
                host = parsed_url.hostname.lower().rstrip(".") if parsed_url else ""
                port = parsed_url.port if parsed_url else None
            except ValueError:
                errors += 1
                continue
            if (
                not parsed_url
                or parsed_url.scheme.lower() != "https"
                or not host
                or parsed_url.username
                or parsed_url.password
                or port not in (None, 443)
                or parsed_url.fragment
            ):
                errors += 1
                continue
            try:
                source_resolver = getattr(
                    self.evidence_correlator, "source_id_for_url", None
                )
                # Production corroborators resolve publisher identity from
                # trusted host policy. Generic test/adaptor doubles without
                # that contract retain the host identifier behavior.
                source_id = source_resolver(article_url) if callable(source_resolver) else host
                evidence = self.evidence_correlator.ingest(
                    item,
                    source_id=source_id,
                    ingested_at=ingested_at,
                )
                processed += 1
                if (
                    self.on_evidence is not None
                    and isinstance(evidence, dict)
                    and evidence.get("evidence_id")
                    and evidence.get("status") != "DUPLICATE_SOURCE_ITEM"
                ):
                    classification = classify_market_news(item)
                    if classification.get("importance") == "HIGH_REVIEW":
                        try:
                            self.on_evidence(item, evidence, classification)
                        except Exception:
                            notification_errors += 1
            except Exception:
                errors += 1

        if errors or feed_coverage_partial:
            state = "PARTIAL"
        else:
            state = "POLL_SUCCEEDED"

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._last_poll_at = now
            # A successful provider fetch is not a successful evidence cycle
            # when one or more returned items fail URL validation or ingestion.
            # Keep the previous success timestamp so readiness can detect a
            # persistently partial pipeline instead of masking it as healthy.
            if live and errors == 0 and not feed_coverage_partial:
                self._last_success_at = now
            self._last_state = state
            self._last_error_class = None
            self._last_item_count = len(items)
            self._last_processed = processed
            self._last_errors = errors
            self._last_notification_errors = notification_errors
            return self.status()

    def latest_items(self) -> tuple[Any, ...]:
        """Return the last polled batch without making another provider request."""
        with self._lock:
            return tuple(self._last_items)

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
                "last_notification_errors": self._last_notification_errors,
                "fact_confirmation": "NEVER_AUTOMATIC",
                "execution_authorized": False,
            }
