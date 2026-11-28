# Curated official news and economic-information feeds

Reviewed on 28 November 2026. This is a starter source catalogue, not a claim of exhaustive global coverage. Each URL below is published or linked by the named official institution. The runtime still requires the operator to configure feed URLs and matching trusted publisher policies explicitly.

## Direct official RSS/Atom endpoints

| Institution | Direct feed URL | Suggested trusted tier | Use |
|---|---|---|---|
| Federal Reserve (United States) | `https://www.federalreserve.gov/feeds/press_all.xml` | `OFFICIAL_PRIMARY` | Monetary-policy statements and press releases |
| European Central Bank | `https://www.ecb.europa.eu/rss/press.html` | `OFFICIAL_PRIMARY` | ECB press releases and policy communications |
| U.S. Bureau of Labor Statistics | `https://www.bls.gov/feed/bls_latest.rss` | `OFFICIAL_PRIMARY` | Employment and inflation statistical releases |
| U.S. Securities and Exchange Commission | `https://www.sec.gov/news/pressreleases.rss` | `OFFICIAL_PRIMARY` | Regulatory announcements and enforcement |
| Bank of Japan — updates | `https://www.boj.or.jp/en/rss/whatsnew.xml` | `OFFICIAL_PRIMARY` | Central-bank updates and policy information |
| Bank of Japan — statistics | `https://www.boj.or.jp/en/rss/statistics.xml` | `OFFICIAL_PRIMARY` | Statistical releases and revisions |
| Bank of Canada — press releases | `https://www.bankofcanada.ca/content_type/press-releases/feed/` | `OFFICIAL_PRIMARY` | Canadian monetary-policy and central-bank communications |

## Official feed directories requiring feed selection

- Banco Central do Brasil: https://www.bcb.gov.br/en/about/rssen — provides feeds for exchange rates, economic indicators, press releases, Copom minutes and other publications. The page is JavaScript-rendered in some clients; copy the exact RSS target from the official page before configuring it.
- Bank of Canada: https://www.bankofcanada.ca/rss-feeds/ — offers separate feeds for announcements, market notices, news, press releases, speeches, publications and exchange-rate information.
- Bank of Japan: https://www.boj.or.jp/en/tips.htm — documents its official general-updates and statistics RSS feeds.
- SEC: https://www.sec.gov/about/rss-feeds — documents press releases, speeches, litigation releases, trading suspensions and EDGAR search feeds.
- BLS: https://www.bls.gov/help/hlp_rss.htm — documents topic-specific feeds in addition to the latest feed.

## Starter environment configuration

The following uses the direct endpoints above. The trusted-source policy must be configured separately from the feed list; never infer source trust from the RSS payload's display name.

```text
CONTROLADOR_NEWS_FEEDS=https://www.federalreserve.gov/feeds/press_all.xml;https://www.ecb.europa.eu/rss/press.html;https://www.bls.gov/feed/bls_latest.rss;https://www.sec.gov/news/pressreleases.rss;https://www.boj.or.jp/en/rss/whatsnew.xml;https://www.boj.or.jp/en/rss/statistics.xml;https://www.bankofcanada.ca/content_type/press-releases/feed/
CONTROLADOR_NEWS_SOURCE_POLICIES=[{"source_id":"federal-reserve","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["federalreserve.gov"],"publisher_group":"federal-reserve"},{"source_id":"ecb","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["ecb.europa.eu"],"publisher_group":"ecb"},{"source_id":"bls","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["bls.gov"],"publisher_group":"us-labor-statistics"},{"source_id":"sec","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["sec.gov"],"publisher_group":"us-sec"},{"source_id":"boj","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["boj.or.jp"],"publisher_group":"boj"},{"source_id":"bank-of-canada","source_tier":"OFFICIAL_PRIMARY","allowed_hosts":["bankofcanada.ca"],"publisher_group":"bank-of-canada"}]
CONTROLADOR_NEWS_POLL_INTERVAL_SECONDS=60
```

## Important coverage limitations

- These are primary institutional sources, not a complete real-time global newswire. Add independent journalism only after verifying the publisher, feed URL, editorial group, access terms and update cadence.
- Official statistical/press feeds often publish scheduled releases rather than breaking news. The polling interval cannot make a publisher release information sooner.
- A feed that is reachable is not proof that its content is complete, current or relevant to every asset.
- The current headline classifier is conservative keyword triage. It does not extract full article claims, measure sentiment, estimate directional impact probabilities or establish causation.
- Headlines from a shared wire or syndicated editorial group must not be counted as independent confirmation. Configure aliases under one `publisher_group`.
- Validate feed access, freshness and item timestamps in the deployed environment before treating a source as active. Do not describe a feed as live until runtime health reports successful collection.
- Do not place credentials, API secrets or private keys in feed URLs or source policy JSON.
