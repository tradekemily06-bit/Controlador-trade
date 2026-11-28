"""Source-aware news evidence clustering without automatic fact confirmation.

This layer preserves each publisher's observation separately. Cross-publisher
matches are review candidates only: headlines are not article verification,
independent corroboration, sentiment, direction, or a trading signal.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Mapping
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
    publisher_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip() or len(self.source_id) > 128:
            raise ValueError("source_id is required")
        if self.source_tier not in _ALLOWED_TIERS:
            raise ValueError("unsupported trusted news source tier")
        if self.publisher_group is not None and (
            not isinstance(self.publisher_group, str)
            or not self.publisher_group.strip()
            or len(self.publisher_group) > 128
        ):
            raise ValueError("publisher_group must be a non-empty trusted identifier")
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


class SQLiteNewsEvidenceStore:
    """Tenant-scoped append-only local store; not a shared multi-replica database."""

    def __init__(self, database_path: str | Path, *, tenant_id: str, subject_id: str) -> None:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not isinstance(subject_id, str) or not subject_id.strip():
            raise ValueError("subject_id is required")
        self.database_path = str(database_path)
        self.tenant_id = tenant_id.strip()
        self.subject_id = subject_id.strip()
        if self.database_path != ":memory:" and Path(self.database_path).is_symlink():
            raise ValueError("news evidence database path must not be a symlink")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_schema(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tenant_news_evidence (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    published_at TEXT,
                    ingested_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, subject_id, evidence_id),
                    UNIQUE (tenant_id, subject_id, source_id, fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tenant_news_evidence_time
                ON tenant_news_evidence (tenant_id, subject_id, published_at)
                """
            )

    def append(self, record: NewsEvidenceRecord) -> bool:
        if not isinstance(record, NewsEvidenceRecord):
            raise ValueError("record must be NewsEvidenceRecord")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO tenant_news_evidence
                (tenant_id, subject_id, evidence_id, source_id, fingerprint,
                 published_at, ingested_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.tenant_id, self.subject_id, record.evidence_id,
                    record.source_id, record.fingerprint,
                    record.published_at.isoformat() if record.published_at else None,
                    record.ingested_at.isoformat(),
                    json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
            return cursor.rowcount == 1

    def load(
        self,
        *,
        since: datetime | None = None,
        limit: int = 5000,
    ) -> list[NewsEvidenceRecord]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50000:
            raise ValueError("news evidence load limit must be between 1 and 50000")
        parameters: list[object] = [self.tenant_id, self.subject_id]
        time_filter = ""
        if since is not None:
            cutoff = _aware_timestamp(since, "since").isoformat()
            time_filter = " AND COALESCE(published_at, ingested_at) >= ?"
            parameters.append(cutoff)
        parameters.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM tenant_news_evidence
                WHERE tenant_id = ? AND subject_id = ?
                """ + time_filter + """
                ORDER BY ingested_at DESC, evidence_id DESC
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
        rows.reverse()
        records = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            published = payload.get("published_at")
            records.append(NewsEvidenceRecord(
                evidence_id=payload["evidence_id"],
                source_id=payload["source_id"],
                source_tier=payload["source_tier"],
                source_host=payload["source_host"],
                title=payload["title"],
                url=payload["url"],
                published_at=datetime.fromisoformat(published) if published else None,
                ingested_at=datetime.fromisoformat(payload["ingested_at"]),
                event_categories=tuple(payload["event_categories"]),
                affected_assets=tuple(payload["affected_assets"]),
                fingerprint=payload["fingerprint"],
                fact_status=payload["fact_status"],
                corroboration_status=payload["corroboration_status"],
                corroborating_source_ids=tuple(payload["corroborating_source_ids"]),
                limitations=tuple(payload["limitations"]),
            ))
        return records


class NewsEvidenceCorroborator:
    """Candidate matcher; persistence is supplied by an owner-scoped store."""

    MAX_IN_MEMORY_RECORDS = 5000

    def __init__(
        self,
        policies: Mapping[str, NewsSourcePolicy],
        *,
        max_age: timedelta = timedelta(hours=72),
        similarity_threshold: float = 0.82,
        store: SQLiteNewsEvidenceStore | None = None,
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
        self._store = store
        self._records: list[NewsEvidenceRecord] = (
            store.load(
                since=datetime.now(timezone.utc) - max_age,
                limit=self.MAX_IN_MEMORY_RECORDS,
            )
            if store is not None else []
        )

    @property
    def store(self) -> SQLiteNewsEvidenceStore | None:
        """Expose the configured persistence adapter for runtime boundary checks."""
        return self._store

    def source_id_for_url(self, url: str) -> str:
        """Resolve an article URL to exactly one trusted configured source policy."""
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("news URL is invalid")
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            raise ValueError("news URL is outside the trusted source host policy")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("news URL has an invalid port") from exc
        if port not in (None, 443):
            raise ValueError("news URL is outside the trusted source host policy")
        matches = [
            source_id
            for source_id, policy in self._policies.items()
            if any(
                host == allowed.strip().lower().rstrip(".")
                or host.endswith("." + allowed.strip().lower().rstrip("."))
                for allowed in policy.allowed_hosts
            )
        ]
        if len(matches) != 1:
            raise ValueError("news URL must resolve to exactly one configured trusted source")
        return matches[0]

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
            if observed - published > self._max_age:
                return {
                    "status": "STALE_SOURCE_ITEM",
                    "fact_status": "UNVERIFIED_REPORT",
                    "execution_authorized": False,
                }

        # Keep matching work bounded to the configured evidence window and a
        # hard cap, while the append-only store remains the durable audit trail.
        cutoff = observed - self._max_age
        self._records = [
            record for record in self._records
            if record.ingested_at >= cutoff
        ][-self.MAX_IN_MEMORY_RECORDS:]

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
                previous_policy = self._policies.get(record.source_id)
                current_group = policy.publisher_group or policy.source_id
                previous_group = (
                    previous_policy.publisher_group or previous_policy.source_id
                    if previous_policy is not None else None
                )
                # Different feed IDs or domains do not prove editorial independence.
                # The host must assign aliases/syndicated feeds to the same group.
                if (
                    record.published_at is None
                    or record.source_id == source_id
                    or previous_group is None
                    or previous_group == current_group
                ):
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
        if self._store is not None and not self._store.append(record):
            return {
                "status": "DUPLICATE_SOURCE_ITEM",
                "fact_status": "UNVERIFIED_REPORT",
                "execution_authorized": False,
            }
        self._records.append(record)
        return record.to_dict() | {"execution_authorized": False}

    def records(self) -> tuple[NewsEvidenceRecord, ...]:
        return tuple(self._records)
