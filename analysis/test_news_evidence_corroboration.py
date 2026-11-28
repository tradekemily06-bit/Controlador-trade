from datetime import datetime, timezone

import pytest

from analysis.news_evidence_corroboration import (
    NewsEvidenceCorroborator,
    NewsSourcePolicy,
)
from integration.rss_news_provider import NewsItem


NOW = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)


def _engine():
    return NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
        "wire-b": NewsSourcePolicy("wire-b", "TRUSTED_MEDIA", ("apnews.com",)),
        "official": NewsSourcePolicy("official", "OFFICIAL_PRIMARY", ("federalreserve.gov",)),
    })


def _item(title, url, published_at="2026-11-28T11:55:00Z"):
    return NewsItem(title, "untrusted payload source label", published_at, url)


def test_news_evidence_uses_trusted_policy_not_provider_source_label():
    result = _engine().ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )

    assert result["source_id"] == "wire-a"
    assert result["source_tier"] == "TRUSTED_MEDIA"
    assert result["source_host"] == "www.reuters.com"
    assert result["fact_status"] == "UNVERIFIED_REPORT"
    assert result["execution_authorized"] is False


def test_second_publisher_creates_candidate_not_confirmed_fact():
    engine = _engine()
    first = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    second = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://apnews.com/article/fed"),
        source_id="wire-b",
        ingested_at=NOW,
    )

    assert first["corroboration_status"] == "SINGLE_SOURCE"
    assert second["corroboration_status"] == "MULTI_SOURCE_CANDIDATE"
    assert second["corroborating_source_ids"] == ["wire-a"]
    assert second["fact_status"] == "UNVERIFIED_REPORT"
    assert "source_independence_not_proven" in second["limitations"]
    assert second["execution_authorized"] is False


def test_same_publisher_duplicate_does_not_count_as_corroboration():
    engine = _engine()
    first = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    duplicate = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed-copy"),
        source_id="wire-a",
        ingested_at=NOW,
    )

    assert duplicate["status"] == "DUPLICATE_SOURCE_ITEM"
    assert duplicate["duplicate_of"] == first["evidence_id"]
    assert len(engine.records()) == 1


def test_unrelated_headlines_do_not_become_corroboration_candidates():
    engine = _engine()
    engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    second = engine.ingest(
        _item("European Central Bank publishes bank supervision report", "https://apnews.com/article/ecb"),
        source_id="wire-b",
        ingested_at=NOW,
    )

    assert second["corroboration_status"] == "SINGLE_SOURCE"
    assert second["corroborating_source_ids"] == []


def test_old_or_missing_publication_timestamp_cannot_corroborate():
    engine = _engine()
    engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed",
              "2026-11-20T11:55:00Z"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    recent = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://apnews.com/article/fed",
              "2026-11-28T11:55:00Z"),
        source_id="wire-b",
        ingested_at=NOW,
    )
    missing = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.federalreserve.gov/newsevents.htm", None),
        source_id="official",
        ingested_at=NOW,
    )

    assert recent["corroboration_status"] == "SINGLE_SOURCE"
    assert missing["corroboration_status"] == "PUBLISHED_TIME_MISSING"


@pytest.mark.parametrize("url", [
    "http://www.reuters.com/story",
    "https://reuters.com.attacker.test/story",
    "https://user:pass@reuters.com/story",
    "https://reuters.com:8443/story",
    "https://127.0.0.1/story",
])
def test_rejects_untrusted_news_source_urls(url):
    with pytest.raises(ValueError):
        _engine().ingest(
            _item("Federal Reserve announces interest rate decision", url),
            source_id="wire-a",
            ingested_at=NOW,
        )


def test_rejects_unknown_source_and_naive_timestamps():
    engine = _engine()
    with pytest.raises(ValueError):
        engine.ingest(
            _item("A market headline", "https://www.reuters.com/story"),
            source_id="unknown",
            ingested_at=NOW,
        )
    with pytest.raises(ValueError):
        engine.ingest(
            _item("A market headline", "https://www.reuters.com/story"),
            source_id="wire-a",
            ingested_at="2026-11-28T12:00:00",
        )


def test_news_policy_rejects_untrusted_or_empty_configuration():
    with pytest.raises(ValueError):
        NewsSourcePolicy("wire", "UNVERIFIED", ("example.com",))
    with pytest.raises(ValueError):
        NewsSourcePolicy("wire", "TRUSTED_MEDIA", ())
