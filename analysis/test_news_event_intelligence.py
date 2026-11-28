from types import SimpleNamespace

import pytest

from analysis.news_event_intelligence import classify_market_news, classify_news_batch


def test_classifies_central_bank_and_currency_without_directional_prediction():
    item = SimpleNamespace(
        title="Federal Reserve rate decision surprises markets",
        source="Official release",
        published_at="2026-11-28T12:00:00+00:00",
        url="https://example.org/story",
    )

    result = classify_market_news(item)

    assert "MONETARY_POLICY" in result["event_categories"]
    assert "USD" in result["affected_assets"]
    assert result["importance"] == "HIGH_REVIEW"
    assert result["sentiment"] == "NOT_ASSESSED"
    assert result["directional_bias"] == "NOT_ASSESSED"
    assert result["probability_impact"] is None
    assert result["execution_authorized"] is False


def test_classifies_event_context_found_in_publisher_feed_summary():
    item = SimpleNamespace(
        title="Central bank publishes policy statement",
        summary="The statement unexpectedly raises interest rates and changes the inflation outlook.",
        source="Official release",
    )

    result = classify_market_news(item)

    assert "MONETARY_POLICY" in result["event_categories"]
    assert "INFLATION" in result["event_categories"]
    assert "USD" in result["affected_assets"]
    assert result["classification_basis"] == "HEADLINE_AND_FEED_SUMMARY_KEYWORD_RULES"
    assert "full_article_not_verified" in result["limitations"]


def test_unknown_headline_is_not_forced_into_an_asset_or_event():
    item = SimpleNamespace(title="A new company opens an office", source="Wire")

    result = classify_market_news(item)

    assert result["affected_assets"] == []
    assert result["event_categories"] == []
    assert result["importance"] == "UNASSESSED"
    assert result["mapping_confidence"] == "NO_MATCH"


def test_classification_batch_preserves_order_and_provenance():
    items = [
        SimpleNamespace(title="Oil supply cut announced by OPEC", source="A"),
        SimpleNamespace(title="Brazil IPCA inflation data released", source="B"),
    ]

    results = classify_news_batch(items)

    assert [item["source"] for item in results] == ["A", "B"]
    assert "OIL" in results[0]["affected_assets"]
    assert "BRL" in results[1]["affected_assets"]
    assert "INFLATION" in results[1]["event_categories"]


def test_empty_headline_is_rejected():
    with pytest.raises(ValueError):
        classify_market_news(SimpleNamespace(title="  ", source="Wire"))


def test_short_tickers_do_not_match_inside_unrelated_words():
    item = SimpleNamespace(title="Whether markets can recover remains uncertain", source="Wire")

    result = classify_market_news(item)

    assert "ETH" not in result["affected_assets"]
    assert result["event_categories"] == []


def test_regulatory_acronym_matches_as_a_complete_token():
    item = SimpleNamespace(title="The SEC announces a new disclosure rule", source="Official")

    result = classify_market_news(item)

    assert "REGULATION" in result["event_categories"]
