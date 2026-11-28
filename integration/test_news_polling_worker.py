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
    def __init__(self, items=None, *, live=True, error=None):
        self.items = list(items or [])
        self.live = live
        self.error = error

    def latest(self, *, limit=10):
        if self.error:
            raise self.error
        return self.items[:limit]

    def status(self):
        return {"configured": True, "live": self.live}


class FakeCorrelator:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def ingest(self, item, *, source_id, ingested_at):
        if self.fail:
            raise RuntimeError("sensitive persistence details")
        self.calls.append((item.title, source_id, ingested_at))


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


def test_news_worker_reports_partial_evidence_failures_without_leaking_details():
    provider = FakeProvider([NewsItem("https://www.reuters.com/story", "Headline")])
    worker = NewsPollingWorker(provider, FakeCorrelator(fail=True), interval_seconds=30)

    status = worker.run_once()

    assert status["last_state"] == "PARTIAL"
    assert status["last_errors"] == 1
    assert "sensitive persistence details" not in str(status)


def test_news_worker_does_not_claim_live_when_provider_is_stale_or_unavailable():
    provider = FakeProvider([NewsItem("https://www.reuters.com/story", "Headline")], live=False)
    worker = NewsPollingWorker(provider, FakeCorrelator(), interval_seconds=30)

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
