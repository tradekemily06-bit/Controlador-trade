"""Conservative, auditable classification of market-news headlines.

This is a rules-based triage layer, not sentiment prediction or an ASI claim.
It never converts a headline into a trading instruction or probability.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


_ASSET_TERMS: dict[str, tuple[str, ...]] = {
    "USD": ("usd", "dollar", "fed", "federal reserve", "treasury", "us inflation", "us cpi", "nonfarm"),
    "EUR": ("eur", "euro", "ecb", "european central bank", "eurozone"),
    "GBP": ("gbp", "pound", "sterling", "bank of england", "boe"),
    "JPY": ("jpy", "yen", "bank of japan", "boj"),
    "CHF": ("chf", "swiss franc", "swiss national bank", "snb"),
    "CAD": ("cad", "canadian dollar", "bank of canada", "boc"),
    "AUD": ("aud", "australian dollar", "reserve bank of australia", "rba"),
    "NZD": ("nzd", "new zealand dollar", "reserve bank of new zealand", "rbnz"),
    "BRL": ("brl", "real brasileiro", "banco central do brasil", "copom", "selic", "ipca", "ibovespa", "b3"),
    "GOLD": ("gold", "ouro", "xau", "bullion"),
    "SILVER": ("silver", "prata", "xag"),
    "OIL": ("oil", "crude", "brent", "wti", "petróleo", "petroleo", "opec"),
    "NATURAL_GAS": ("natural gas", "gás natural", "gas natural"),
    "BTC": ("bitcoin", "btc"),
    "ETH": ("ethereum", "ether", "eth"),
    "EQUITIES": ("stock market", "equities", "shares", "wall street", "s&p 500", "nasdaq", "dow jones"),
}


_EVENT_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MONETARY_POLICY", ("interest rate", "rate decision", "central bank", "fed", "ecb", "copom", "selic", "monetary policy", "juros")),
    ("INFLATION", ("inflation", "cpi", "ppi", "consumer prices", "producer prices", "ipca")),
    ("EMPLOYMENT", ("employment", "jobs report", "nonfarm", "unemployment", "payroll", "jobless claims", "emprego")),
    ("GDP_GROWTH", ("gdp", "gross domestic product", "economic growth", "pib")),
    ("GEOPOLITICS", ("war", "sanction", "invasion", "conflict", "attack", "ceasefire", "geopolitical")),
    ("ENERGY_SUPPLY", ("opec", "oil production", "supply cut", "pipeline", "energy supply")),
    ("CORPORATE", ("earnings", "quarterly results", "revenue", "profit warning", "merger", "acquisition")),
    ("REGULATION", ("regulator", "regulation", "lawsuit", "sec ", "cftc", "antitrust", "ban", "approval")),
)


_HIGH_IMPACT_TERMS = (
    "emergency", "unexpected", "surprise", "crisis", "default", "halt", "intervention",
    "rate decision", "interest rate", "inflation", "nonfarm", "war", "sanction",
    "bank failure", "bank collapse", "opec", "rate hike", "rate cut",
)


def _normalise(value: str) -> str:
    return re.sub(r"\\s+", " ", value.casefold()).strip()


def classify_market_news(item: Any) -> dict[str, Any]:
    """Classify a NewsItem-like object using headline-only transparent rules."""
    title = getattr(item, "title", "")
    source = getattr(item, "source", "")
    published_at = getattr(item, "published_at", None)
    url = getattr(item, "url", None)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("news headline is required")
    text = _normalise(title)
    assets = sorted({
        asset
        for asset, terms in _ASSET_TERMS.items()
        if any(_normalise(term) in text for term in terms)
    })
    categories = [
        category for category, terms in _EVENT_TERMS
        if any(_normalise(term) in text for term in terms)
    ]
    high_impact = any(_normalise(term) in text for term in _HIGH_IMPACT_TERMS)
    if high_impact:
        importance = "HIGH_REVIEW"
    elif categories or assets:
        importance = "MEDIUM_REVIEW"
    else:
        importance = "UNASSESSED"
    if len(assets) == 1 and categories:
        mapping_confidence = "RULE_MATCH"
    elif assets or categories:
        mapping_confidence = "AMBIGUOUS_RULE_MATCH"
    else:
        mapping_confidence = "NO_MATCH"
    return {
        "title": title,
        "source": source if isinstance(source, str) else None,
        "published_at": published_at,
        "url": url,
        "event_categories": categories,
        "affected_assets": assets,
        "importance": importance,
        "classification_basis": "HEADLINE_KEYWORD_RULES",
        "mapping_confidence": mapping_confidence,
        "sentiment": "NOT_ASSESSED",
        "directional_bias": "NOT_ASSESSED",
        "probability_impact": None,
        "execution_authorized": False,
        "limitations": [
            "headline_only_classification",
            "not_verified_against_full_article",
            "not_a_price_forecast",
            "not_a_trading_instruction",
        ],
    }


def classify_news_batch(items: Iterable[Any]) -> list[dict[str, Any]]:
    """Classify a batch while preserving provider order and provenance."""
    return [classify_market_news(item) for item in items]
