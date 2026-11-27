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
