from datetime import datetime, timezone

import pytest

from analysis.news_evidence_corroboration import (
    NewsEvidenceCorroborator,
    NewsSourcePolicy,
    SQLiteNewsEvidenceStore,
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


def test_source_id_for_url_resolves_exactly_one_trusted_publisher_policy():
    engine = _engine()
    assert engine.source_id_for_url("https://www.reuters.com/markets/fed") == "wire-a"
    assert engine.source_id_for_url("https://apnews.com/article/fed") == "wire-b"


def test_source_id_for_url_rejects_unknown_or_ambiguous_publisher_hosts():
    engine = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
        "wire-a-copy": NewsSourcePolicy("wire-a-copy", "TRUSTED_MEDIA", ("reuters.com",)),
    })
    with pytest.raises(ValueError):
        engine.source_id_for_url("https://www.reuters.com/story")
    with pytest.raises(ValueError):
        _engine().source_id_for_url("https://unknown.example/story")


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
    # The missing-publication-time item remains in the audit history but cannot corroborate.


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



def test_owner_scoped_sqlite_store_recovers_evidence_after_restart(tmp_path):
    database = tmp_path / "news-evidence.sqlite3"
    store = SQLiteNewsEvidenceStore(database, tenant_id="tenant-a", subject_id="alice")
    store.initialize_schema()
    first_engine = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
        "wire-b": NewsSourcePolicy("wire-b", "TRUSTED_MEDIA", ("apnews.com",)),
    }, store=store)
    assert first_engine.store is store
    first = first_engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )

    restarted_store = SQLiteNewsEvidenceStore(database, tenant_id="tenant-a", subject_id="alice")
    restarted_engine = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
        "wire-b": NewsSourcePolicy("wire-b", "TRUSTED_MEDIA", ("apnews.com",)),
    }, store=restarted_store)
    second = restarted_engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://apnews.com/article/fed"),
        source_id="wire-b",
        ingested_at=NOW,
    )
    duplicate = restarted_engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed-copy"),
        source_id="wire-a",
        ingested_at=NOW,
    )

    assert first["fact_status"] == "UNVERIFIED_REPORT"
    assert second["corroboration_status"] == "MULTI_SOURCE_CANDIDATE"
    assert second["corroborating_source_ids"] == ["wire-a"]
    assert duplicate["status"] == "DUPLICATE_SOURCE_ITEM"
    assert len(restarted_engine.records()) == 2
    assert len(restarted_store.load(limit=1)) == 1


def test_sqlite_news_evidence_isolation_between_tenants(tmp_path):
    database = tmp_path / "news-evidence.sqlite3"
    owner_a = SQLiteNewsEvidenceStore(database, tenant_id="tenant-a", subject_id="alice")
    owner_b = SQLiteNewsEvidenceStore(database, tenant_id="tenant-b", subject_id="bob")
    owner_a.initialize_schema()
    owner_b.initialize_schema()
    engine_a = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
    }, store=owner_a)
    engine_a.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    engine_b = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy("wire-a", "TRUSTED_MEDIA", ("reuters.com",)),
    }, store=owner_b)

    assert len(engine_a.records()) == 1
    assert engine_b.records() == ()
    assert owner_b.load() == []


def test_sqlite_news_evidence_requires_owner_and_rejects_symlink(tmp_path):
    with pytest.raises(ValueError):
        SQLiteNewsEvidenceStore(tmp_path / "news.sqlite3", tenant_id="", subject_id="alice")
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "news-link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        SQLiteNewsEvidenceStore(link, tenant_id="tenant-a", subject_id="alice")


def test_syndicated_feeds_from_same_publisher_group_do_not_count_as_independent():
    engine = NewsEvidenceCorroborator({
        "wire-a": NewsSourcePolicy(
            "wire-a", "TRUSTED_MEDIA", ("reuters.com",), publisher_group="reuters-editorial"
        ),
        "wire-a-syndicated": NewsSourcePolicy(
            "wire-a-syndicated", "TRUSTED_MEDIA", ("reuters.com",),
            publisher_group="reuters-editorial",
        ),
    })
    engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://www.reuters.com/markets/fed"),
        source_id="wire-a",
        ingested_at=NOW,
    )
    second = engine.ingest(
        _item("Federal Reserve announces interest rate decision", "https://reuters.com/world/fed-decision"),
        source_id="wire-a-syndicated",
        ingested_at=NOW,
    )

    assert second["corroboration_status"] == "SINGLE_SOURCE"
    assert second["corroborating_source_ids"] == []
    assert "source_independence_not_proven" in second["limitations"]
