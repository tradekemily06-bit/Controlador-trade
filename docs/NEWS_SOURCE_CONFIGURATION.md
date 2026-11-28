# News source configuration

The standalone runtime does not silently trust every RSS publisher. News feed retrieval and publisher trust are separate controls.

## Runtime behavior

- `CONTROLADOR_NEWS_FEEDS` is a semicolon-separated list of HTTPS RSS/Atom feed URLs. Only domains in the RSS provider allowlist are accepted; redirects, non-standard ports, embedded credentials and unsafe DNS answers are rejected.
- `CONTROLADOR_NEWS_SOURCE_POLICIES` is a JSON array defining trusted publisher identities. Each item requires `source_id`, `source_tier` (`OFFICIAL_PRIMARY`, `TRUSTED_MEDIA` or `COMMENTARY`) and `allowed_hosts`; `publisher_group` is optional.
- When explicit source policies are present, the runtime creates an owner-scoped SQLite evidence store at `news-evidence.sqlite3` inside the runtime directory. The store is included in the runtime's local backup/readiness inventory.
- The bounded news polling worker starts only when both a configured RSS provider and trusted evidence correlator are available. Its default interval is 60 seconds (30–3600 seconds allowed), with at most 50 headlines per poll.
- Invalid JSON, invalid trust tiers, duplicate source IDs, duplicate hosts and overlapping parent/subdomain trust scopes fail startup. Missing policy disables evidence polling; it does not downgrade unknown publishers to trusted sources.

## Example configuration

The URLs below are official publisher feeds documented by their publishers:

```text
CONTROLADOR_NEWS_FEEDS=https://www.federalreserve.gov/feeds/press_all.xml;https://www.ecb.europa.eu/rss/press.html
CONTROLADOR_NEWS_SOURCE_POLICIES=[{"source_id":"federal-reserve","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["federalreserve.gov"],"publisher_group":"us-central-bank"},{"source_id":"ecb","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["ecb.europa.eu"],"publisher_group":"euro-central-bank"}]
CONTROLADOR_NEWS_POLL_INTERVAL_SECONDS=60
```

The example is a starter configuration, not a complete global news universe. Additional sources should be added only after checking the publisher's official feed URL, domain ownership, update cadence, access terms and publisher group. Do not label a media outlet as an official primary source.

## Evidence and decision limits

The current pipeline stores headline-level evidence with publisher identity, source URL, publication/ingestion timestamps, conservative event categories and potentially affected assets. Similar headlines from different configured publishers become review candidates; they are not proof of independent confirmation. Headlines are not full-article verification, sentiment, market direction, impact probability or a trading instruction.

Full-article retrieval/claim extraction, official economic-calendar adapters, hosted worker continuity, shared production database/KMS, and live end-to-end source acceptance remain separate release gates. The current SQLite implementation is single-runtime/single-host only. The worker stops with its runtime process; it is not an always-on cloud service until deployed under a persistent hosted supervisor.

## Publisher documentation

- Federal Reserve RSS feeds: https://www.federalreserve.gov/feeds/feeds.htm
- European Central Bank RSS feeds: https://www.ecb.europa.eu/home/html/rss.en.html
- Banco Central do Brasil RSS feeds: https://www.bcb.gov.br/en/about/rssen


## App read path and high-impact alerts

When the standalone runtime has both the RSS provider and trusted publisher policies configured, the background worker is the only component that polls feeds and ingests evidence. The Analysis/news read path consumes the worker's latest in-memory batch and already-persisted evidence; it does not trigger another poll or mutate evidence on page read.

The API exposes whether the cached batch is current, stale, or absent, plus the worker's last collection state. If only some configured feeds succeed, the cycle is marked partial and is not reported as fully live.

Newly persisted headlines classified by conservative rules as `HIGH_REVIEW` can produce an owner-scoped market notification. Notifications are deduplicated by evidence ID and explicitly state that the headline is unverified and is not a price forecast or trading instruction. Duplicate headlines and lower-review classifications do not create this alert. Notification sink errors are tracked separately from evidence ingestion failures.

The worker cache is process-local. After a process restart, the evidence archive remains in SQLite, but the latest headline batch is not advertised as current until a new successful poll completes. Hosted continuity and cross-replica cache sharing are still deployment work.


## Evidence memory bounds

The active in-memory corroboration window loads at most the most recent 72 hours and 5,000 records. Older published headlines remain in the append-only tenant SQLite audit store but are not loaded into active matching memory or treated as recent corroboration. This bounds restart-time matching work; it does not impose a disk-retention or archive-compaction policy.
