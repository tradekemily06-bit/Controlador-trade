from __future__ import annotations

from dataclasses import dataclass
from threading import Event

import pytest

from integration.news_polling_worker import NewsPollingWorker


@dataclass
class NewsItem:
    url: str
    title: str


class FakeProvider:
    def __init__(
        self, items=None, *, live=True, error=None, feed_count=None, successful_feeds=None
    ):
        self.items = list(items or [])
        self.live = live
        self.error = error
        self.feed_count = feed_count
        self.successful_feeds = successful_feeds

    def latest(self, *, limit=10):
        if self.error:
            raise self.error
        return self.items[:limit]

    def status(self):
        return {
            "configured": True,
            "live": self.live,
            "feed_count": self.feed_count if self.feed_count is not None else (1 if self.live else 0),
            "successful_feeds": (
                self.successful_feeds
                if self.successful_feeds is not None
                else (1 if self.live else 0)
            ),
        }


class FakeCorrelator:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def ingest(self, item, *, source_id, ingested_at):
        if self.fail:
            raise RuntimeError("sensitive persistence details")
        self.calls.append((item.title, source_id, ingested_at))
        return {"evidence_id": f"evidence-{len(self.calls)}"}


def test_news_worker_persists_headline_evidence_from_trusted_provider_items():
    item = NewsItem("https://www.reuters.com/world/economy/story", "Inflation data")
    provider = FakeProvider([item])
    correlator = FakeCorrelator()
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "POLL_SUCCEEDED"
    assert status["last_item_count"] == 1
    assert status["last_processed"] == 1
    assert correlator.calls[0][1] == "www.reuters.com"
    assert status["fact_confirmation"] == "NEVER_AUTOMATIC"
    assert worker.latest_items() == (item,)


def test_news_worker_uses_trusted_publisher_policy_identifier_when_available():
    item = NewsItem("https://www.reuters.com/world/economy/story", "Inflation data")
    provider = FakeProvider([item])
    correlator = FakeCorrelator()
    correlator.source_id_for_url = lambda url: "trusted-reuters"
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "POLL_SUCCEEDED"
    assert correlator.calls[0][1] == "trusted-reuters"


def test_news_worker_reports_partial_evidence_failures_without_leaking_details():
    provider = FakeProvider([NewsItem("https://www.reuters.com/story", "Headline")])
    worker = NewsPollingWorker(provider, FakeCorrelator(fail=True), interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "PARTIAL"
    assert status["last_errors"] == 1
    assert "sensitive persistence details" not in str(status)


def test_news_worker_does_not_claim_live_when_provider_is_stale_or_unavailable():
    provider = FakeProvider([NewsItem("https://www.reuters.com/story", "Headline")], live=False)
    correlator = FakeCorrelator()
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "SOURCE_UNAVAILABLE"
    assert status["last_success_at"] is None
    assert status["last_processed"] == 0
    assert correlator.calls == []


def test_news_worker_redacts_provider_exceptions():
    provider = FakeProvider(error=TimeoutError("secret URL and token"))
    worker = NewsPollingWorker(provider, FakeCorrelator(), interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "POLL_FAILED"
    assert status["last_error_class"] == "TimeoutError"
    assert "secret URL" not in str(status)


def test_news_worker_rejects_invalid_interval_and_limit():
    provider = FakeProvider()
    correlator = FakeCorrelator()
    for interval in (float("nan"), float("inf"), 1, 3601, True):
        with pytest.raises(ValueError):
            NewsPollingWorker(provider, correlator, interval_seconds=interval)
    with pytest.raises(ValueError):
        NewsPollingWorker(provider, correlator, limit=51)


def test_news_worker_starts_and_stops_cleanly():
    called = Event()
    provider = FakeProvider([NewsItem("https://www.reuters.com/story", "Headline")])
    correlator = FakeCorrelator()
    original_latest = provider.latest

    def latest(*, limit=10):
        called.set()
        return original_latest(limit=limit)

    provider.latest = latest
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)
    worker.start()

    assert called.wait(timeout=2)
    worker.stop(timeout=2)

    assert worker.status()["worker_running"] is False



@pytest.mark.parametrize(
    "url",
    [
        "http://www.reuters.com/story",
        "https://user@www.reuters.com/story",
        "https://www.reuters.com:8443/story",
        "https://www.reuters.com/story#fragment",
        "https://[invalid/story",
    ],
)
def test_news_worker_rejects_unsafe_or_malformed_article_urls(url):
    provider = FakeProvider([NewsItem(url, "Headline")])
    correlator = FakeCorrelator()
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "PARTIAL"
    assert status["last_errors"] == 1
    assert correlator.calls == []


def test_news_worker_marks_partial_feed_coverage_as_partial_not_healthy():
    item = NewsItem("https://www.reuters.com/story", "Headline")
    provider = FakeProvider(
        [item], live=True, feed_count=3, successful_feeds=2
    )
    correlator = FakeCorrelator()
    worker = NewsPollingWorker(provider, correlator, interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "PARTIAL"
    assert status["last_success_at"] is None
    assert status["last_processed"] == 1
    assert worker.latest_items() == (item,)


def test_news_worker_notifies_only_new_high_impact_persisted_evidence():
    item = NewsItem(
        "https://www.reuters.com/world/economy/story",
        "Fed emergency rate decision surprises markets",
    )
    provider = FakeProvider([item])
    correlator = FakeCorrelator()
    alerts = []
    worker = NewsPollingWorker(
        provider, correlator, interval_seconds=30,
        on_evidence=lambda news, evidence, classification: alerts.append(
            (news.title, evidence["evidence_id"], classification["importance"])
        ),
    )

    status = worker.run_once()

    assert status["last_state"] == "POLL_SUCCEEDED"
    assert alerts == [(item.title, "evidence-1", "HIGH_REVIEW")]
    assert status["last_notification_errors"] == 0


def test_news_worker_does_not_alert_on_duplicate_or_non_high_impact_headlines():
    low_item = NewsItem("https://www.reuters.com/story", "Company reports quarterly revenue")
    provider = FakeProvider([low_item])
    correlator = FakeCorrelator()
    alerts = []
    worker = NewsPollingWorker(
        provider, correlator, interval_seconds=30,
        on_evidence=lambda *args: alerts.append(args),
    )
    worker.run_once()
    assert alerts == []

    class DuplicateCorrelator(FakeCorrelator):
        def ingest(self, item, *, source_id, ingested_at):
            self.calls.append((item.title, source_id, ingested_at))
            return {"status": "DUPLICATE_SOURCE_ITEM"}

    high_item = NewsItem("https://www.reuters.com/story", "Fed emergency rate decision")
    duplicate_worker = NewsPollingWorker(
        FakeProvider([high_item]),
        DuplicateCorrelator(),
        interval_seconds=30,
        on_evidence=lambda *args: alerts.append(args),
    )
    duplicate_worker.run_once()
    assert alerts == []


def test_news_worker_separates_notification_failure_from_evidence_ingestion():
    item = NewsItem("https://www.reuters.com/story", "Fed emergency rate decision")
    worker = NewsPollingWorker(
        FakeProvider([item]),
        FakeCorrelator(),
        interval_seconds=30,
        on_evidence=lambda *args: (_ for _ in ()).throw(RuntimeError("private sink detail")),
    )

    status = worker.run_once()

    assert status["last_state"] == "POLL_SUCCEEDED"
    assert status["last_notification_errors"] == 1
    assert "private sink detail" not in str(status)
