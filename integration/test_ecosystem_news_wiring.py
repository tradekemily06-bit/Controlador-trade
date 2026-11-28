from dataclasses import dataclass

from analysis.decision_store import DecisionStore
from integration.ecosystem_service import EcosystemService
from integration.rss_news_provider import NewsItem, NewsProvider


class FakeNewsProvider(NewsProvider):
    def __init__(self):
        self.fetch_count = 0

    def latest(self, *, symbol=None, limit=10):
        self.fetch_count += 1
        return [NewsItem("EURUSD outlook", "Test Wire", "2026-11-26T12:00:00+00:00", "https://example.test/story")]

    def status(self):
        return {"configured": True, "live": True, "feed_count": 1, "successful_feeds": 1}


def test_ecosystem_service_injects_news_and_reports_real_provider_state(tmp_path):
    provider = FakeNewsProvider()
    service = EcosystemService(
        decision_store=DecisionStore(str(tmp_path / "decisions.sqlite3")),
        news_provider=provider,
    )

    risk = service.risk_status()
    assert risk["news_provider"] == "RSS_ATOM"
    assert provider.fetch_count == 0

    result = service.news_status(limit=5, symbol="EURUSD")
    assert result["provider"] == "RSS_ATOM"
    assert result["configured"] is True
    assert result["live"] is True
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == "EURUSD outlook"
    assert provider.fetch_count == 1


class FakePollingWorker:
    def __init__(self, items, state="POLL_SUCCEEDED"):
        self.items = tuple(items)
        self.state = state

    def latest_items(self):
        return self.items

    def status(self):
        return {
            "configured": True,
            "worker_running": True,
            "last_state": self.state,
            "last_success_at": "2026-11-28T12:00:00+00:00" if self.state == "POLL_SUCCEEDED" else None,
            "last_processed": len(self.items),
            "last_errors": 0,
        }


class FakeEvidenceRecord:
    def to_dict(self):
        return {
            "evidence_id": "evidence-1",
            "title": "EURUSD outlook",
            "affected_assets": ["EUR", "USD"],
            "fact_status": "UNVERIFIED_REPORT",
            "corroboration_status": "SINGLE_SOURCE",
        }


class FakeEvidenceCorrelator:
    def __init__(self):
        self.ingest_calls = 0

    def records(self):
        return (FakeEvidenceRecord(),)

    def ingest(self, *args, **kwargs):
        self.ingest_calls += 1
        raise AssertionError("news reads must not ingest or mutate evidence")


def test_standalone_news_reads_cached_worker_batch_without_refetching_provider():
    provider = FakeNewsProvider()
    item = NewsItem(
        "EURUSD outlook",
        "Test Wire",
        "2026-11-28T11:59:00+00:00",
        "https://example.test/story",
    )
    service = EcosystemService(
        decision_store=DecisionStore(":memory:"),
        news_provider=provider,
    )
    service.news_polling_worker = FakePollingWorker([item])

    result = service.news_status(limit=5, symbol="EURUSD")

    assert result["live"] is True
    assert result["items_freshness"] == "CURRENT"
    assert result["collection"]["last_state"] == "POLL_SUCCEEDED"
    assert result["items"][0]["title"] == "EURUSD outlook"
    assert provider.fetch_count == 0


def test_news_read_returns_persisted_evidence_without_ingesting_again():
    provider = FakeNewsProvider()
    correlator = FakeEvidenceCorrelator()
    service = EcosystemService(
        decision_store=DecisionStore(":memory:"),
        news_provider=provider,
        news_evidence_correlator=correlator,
    )
    service.news_polling_worker = FakePollingWorker([
        NewsItem("EURUSD outlook", "Test Wire", "2026-11-28T11:59:00+00:00", "https://example.test/story")
    ])

    result = service.news_status(limit=5, symbol="EURUSD")

    assert result["evidence_processing"]["status"] == "CONNECTED"
    assert result["evidence_processing"]["processed"] == 1
    assert result["evidence_processing"]["records"][0]["fact_status"] == "UNVERIFIED_REPORT"
    assert correlator.ingest_calls == 0
    assert provider.fetch_count == 0


def test_partial_news_collection_is_not_reported_as_live():
    provider = FakeNewsProvider()
    service = EcosystemService(
        decision_store=DecisionStore(":memory:"),
        news_provider=provider,
    )
    service.news_polling_worker = FakePollingWorker([], state="PARTIAL")

    result = service.news_status(limit=5)

    assert result["live"] is False
    assert result["items_freshness"] == "NO_DATA"
    assert result["collection"]["last_state"] == "PARTIAL"


def test_managed_runtime_without_worker_never_falls_back_to_request_time_feed_polling():
    provider = FakeNewsProvider()
    service = EcosystemService(
        decision_store=DecisionStore(":memory:"),
        news_provider=provider,
    )
    service.news_polling_managed = True

    result = service.news_status(limit=5)

    assert result["configured"] is True
    assert result["live"] is False
    assert result["items_freshness"] == "NO_DATA"
    assert result["items"] == []
    assert provider.fetch_count == 0
