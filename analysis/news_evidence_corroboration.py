"""Source-aware news evidence clustering without automatic fact confirmation.

This layer preserves each publisher's observation separately. Cross-publisher
matches are review candidates only: headlines are not article verification,
independent corroboration, sentiment, direction, or a trading signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Iterable, Mapping
from urllib.parse import urlparse

from integration.rss_news_provider import NewsItem
from analysis.news_event_intelligence import classify_market_news


_ALLOWED_TIERS = {"OFFICIAL_PRIMARY", "TRUSTED_MEDIA", "COMMENTARY"}
_WORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "the", "to", "with", "de", "da", "do", "e",
    "em", "no", "na", "nos", "nas", "um", "uma", "para", "por",
}


def _aware_timestamp(value: str | datetime, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{field} must be timezone-aware")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _tokens(title: str) -> frozenset[str]:
    normalized = _WORD.sub(" ", title.casefold())
    return frozenset(token for token in normalized.split() if len(token) > 1 and token not in _STOP_WORDS)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True)
class NewsSourcePolicy:
    """Trusted host configuration; never construct this from an RSS item."""

    source_id: str
    source_tier: str
    allowed_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip() or len(self.source_id) > 128:
            raise ValueError("source_id is required")
        if self.source_tier not in _ALLOWED_TIERS:
            raise ValueError("unsupported trusted news source tier")
        if not isinstance(self.allowed_hosts, tuple) or not self.allowed_hosts:
            raise ValueError("allowed_hosts must be a non-empty tuple")
        for host in self.allowed_hosts:
            if not isinstance(host, str) or not host.strip():
                raise ValueError("invalid trusted news host")
            normalized = host.strip().lower().rstrip(".")
            if "/" in normalized or ":" in normalized or "@" in normalized:
                raise ValueError("trusted news host must be a hostname only")


@dataclass(frozen=True)
class NewsEvidenceRecord:
    evidence_id: str
    source_id: str
    source_tier: str
    source_host: str
    title: str
    url: str
    published_at: datetime | None
    ingested_at: datetime
    event_categories: tuple[str, ...]
    affected_assets: tuple[str, ...]
    fingerprint: str
    fact_status: str
    corroboration_status: str
    corroborating_source_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "source_tier": self.source_tier,
            "source_host": self.source_host,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ingested_at": self.ingested_at.isoformat(),
            "event_categories": list(self.event_categories),
            "affected_assets": list(self.affected_assets),
            "fingerprint": self.fingerprint,
            "fact_status": self.fact_status,
            "corroboration_status": self.corroboration_status,
            "corroborating_source_ids": list(self.corroborating_source_ids),
            "limitations": list(self.limitations),
        }


class NewsEvidenceCorroborator:
    """In-memory candidate matcher; persistence and article review are separate."""

    def __init__(
        self,
        policies: Mapping[str, NewsSourcePolicy],
        *,
        max_age: timedelta = timedelta(hours=72),
        similarity_threshold: float = 0.82,
    ) -> None:
        if not policies or any(key != policy.source_id for key, policy in policies.items()):
            raise ValueError("policies must be keyed by their trusted source_id")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        if not 0.5 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.5 and 1.0")
        self._policies = dict(policies)
        self._max_age = max_age
        self._similarity_threshold = similarity_threshold
        self._records: list[NewsEvidenceRecord] = []

    @staticmethod
    def _validate_url(url: str, policy: NewsSourcePolicy) -> tuple[str, str]:
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("news URL is invalid")
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed = tuple(item.strip().lower().rstrip(".") for item in policy.allowed_hosts)
        if (
            parsed.scheme.lower() != "https" or not host
            or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not any(host == item or host.endswith("." + item) for item in allowed)
        ):
            raise ValueError("news URL is outside the trusted source host policy")
        return url.strip(), host

    def ingest(
        self,
        item: NewsItem,
        *,
        source_id: str,
        ingested_at: str | datetime,
    ) -> dict[str, object]:
        policy = self._policies.get(source_id)
        if policy is None:
            raise ValueError("news source is not configured")
        if not isinstance(item, NewsItem) or not isinstance(item.title, str) or not item.title.strip():
            raise ValueError("a valid NewsItem headline is required")
        if not isinstance(item.url, str):
            raise ValueError("news item must include a source URL")
        url, host = self._validate_url(item.url, policy)
        observed = _aware_timestamp(ingested_at, "ingested_at")
        published = None
        if item.published_at is not None:
            published = _aware_timestamp(item.published_at, "published_at")
            if published > observed + timedelta(minutes=5):
                raise ValueError("published_at cannot be materially in the future")

        tokens = _tokens(item.title)
        canonical = " ".join(sorted(tokens))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        duplicate = next(
            (
                record for record in self._records
                if record.source_id == source_id and record.fingerprint == fingerprint
            ),
            None,
        )
        if duplicate is not None:
            return {
                "status": "DUPLICATE_SOURCE_ITEM",
                "duplicate_of": duplicate.evidence_id,
                "fact_status": "UNVERIFIED_REPORT",
                "execution_authorized": False,
            }

        classified = classify_market_news(item)
        evidence_id = hashlib.sha256(
            f"{source_id}|{url}|{published.isoformat() if published else ''}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        corroborating: set[str] = set()
        if published is not None:
            for record in self._records:
                if record.published_at is None or record.source_id == source_id:
                    continue
                if abs((published - record.published_at).total_seconds()) > self._max_age.total_seconds():
                    continue
                if tuple(classified["event_categories"]) != record.event_categories:
                    continue
                if tuple(classified["affected_assets"]) != record.affected_assets:
                    continue
                if _similarity(tokens, _tokens(record.title)) >= self._similarity_threshold:
                    corroborating.add(record.source_id)

        status = "MULTI_SOURCE_CANDIDATE" if corroborating else (
            "SINGLE_SOURCE" if published is not None else "PUBLISHED_TIME_MISSING"
        )
        record = NewsEvidenceRecord(
            evidence_id=evidence_id,
            source_id=policy.source_id,
            source_tier=policy.source_tier,
            source_host=host,
            title=item.title.strip(),
            url=url,
            published_at=published,
            ingested_at=observed,
            event_categories=tuple(classified["event_categories"]),
            affected_assets=tuple(classified["affected_assets"]),
            fingerprint=fingerprint,
            fact_status="UNVERIFIED_REPORT",
            corroboration_status=status,
            corroborating_source_ids=tuple(sorted(corroborating)),
            limitations=(
                "headline_only",
                "full_article_not_verified",
                "source_independence_not_proven",
                "candidate_match_is_not_fact_confirmation",
                "no_sentiment_or_direction_inferred",
            ),
        )
        self._records.append(record)
        return record.to_dict() | {"execution_authorized": False}

    def records(self) -> tuple[NewsEvidenceRecord, ...]:
        return tuple(self._records)
