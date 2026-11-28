# Implementation completion ledger — 28 November 2026

This ledger is the continuity register for all work already started in the standalone Ecossistema. It is additive: it does not replace existing modules, prior decisions, or the approved Lovable interface. A feature is not complete merely because code or a draft PR exists.

## Non-negotiable product decisions

- One standalone, broker-neutral application; no EA dependency.
- Preserve the existing Lovable interface exactly. No redesign, renamed sections, new navigation area, or fake live values.
- Exactly six visible areas, in order: Cabine de Comando; Análise; Estudo; Reserva Fiscal; Assistente do Ecossistema; Central.
- Decision memory, learning, context graph, audit and orchestration are internal capabilities, not extra visible areas.
- Keep all mapped modules and existing capabilities. Reuse and integrate them in their correct areas; do not delete, silently omit, duplicate, or replace them with placeholders.
- Assistente do Ecossistema remains read-only: no orders and no movement of money.
- No FOMO or urgency manipulation.
- SIMULAÇÃO remains the operating mode. REAL dispatch, order submission and money movement remain disabled in this foundation.

## Repository continuity audit

| PR | Branch | Base | Scope | Integration status |
|---|---|---|---|---|
| [#529](https://github.com/tradekemily06-bit/Controlador-trade/pull/529) | feat/unified-intelligence-standalone-app | main | Standalone application, shared intelligence, assistant, fiscal queues, decision/learning persistence, notifications, API/PWA foundation | Open draft; foundational parent |
| [#531](https://github.com/tradekemily06-bit/Controlador-trade/pull/531) | work/multi-provider-foundation | #529 branch | Tenant-isolated provider sessions, MT5 relay, TradingView alerts, cTrader read-only/OAuth/live market streams, timeframe workers, outcome evidence, tenant notifications | Open draft; inherited through #533 |
| [#532](https://github.com/tradekemily06-bit/Controlador-trade/pull/532) | work/foundation-readiness-audit | #531 branch | Identity/storage readiness, SQLite backup/restore and multi-replica topology guard | Open draft; sibling source. Its relevant code, tests and deployment documentation have been reconciled into #534; do not merge this sibling independently |
| [#533](https://github.com/tradekemily06-bit/Controlador-trade/pull/533) | fix/webpush-encryption-key-readiness | #531 branch | Authenticated browser push routes, encrypted PostgreSQL subscription storage, pywebpush sender, browser client/service worker | Open draft; direct base of #534 |
| [#534](https://github.com/tradekemily06-bit/Controlador-trade/pull/534) | fix/six-visible-areas-memory-capability | #533 branch | Six-area contract, memory as internal capability, news event triage, foundation-readiness reconciliation, backup/restore hardening and advanced-intelligence acceptance target | Active integration candidate; open draft, unmerged |

Integration path: #529 -> #531 -> #533 -> #534. #532 is a sibling of #533, not an ancestor; its relevant foundation changes have been manually reconciled into #534 with tests and documentation. Do not merge drafts automatically or merge #532 separately without reconciling duplicate changes.

## Front 1 — Foundation, persistence, identity and runtime

- [x] Reconcile the #532 readiness audit into the active #534 integration branch: tenant market-data and TradingView stores, MT5 relay tokens, TradingView webhook secrets, cTrader OAuth state/token stores, tenant signal evidence/outcomes, fenced notification outbox schema, scheduled-backup status, expanded read-only store/schema checks, trusted-identity status, and restore verification/regression tests are present on the branch.
- [x] Expand the SQLite backup allowlist for tenant market monitor, TradingView alert history, MT5 relay tokens, TradingView webhook secret hashes, cTrader OAuth state/token stores, tenant signal evidence/outcomes, tenant forecast audit, optional security audit, owner-scoped news evidence and economic-calendar observations. Optional stores report NOT_INITIALIZED when unused rather than false backup failures.
- [x] Add read-only integrity/schema checks for signal evidence, forecast audit, security audit, news evidence and economic-calendar stores. Optional stores report MISSING without degrading required-store readiness; if present, schema and integrity are checked.
- [x] Reconcile the full SQLite backup allowlist with the standalone readiness inventory: all 18 database IDs now have matching filenames and schema checks; all six optional stores share the same optional/not-initialized semantics.
- [x] Verify backup restore on an isolated temporary copy, without modifying the live database; reject corrupt and symlink backup inputs in automated tests.
- [ ] Verify one production-grade shared database, migrations, tenant isolation, durable audit, distributed leases and transaction boundaries; SQLite remains single-host/single-runtime only.
- [x] Integrate the injected economic-calendar polling worker into StandaloneRuntime startup/shutdown and failed-startup cleanup; a stuck worker keeps the runtime process lock held.
- [x] Add the RSS news-evidence polling worker to StandaloneRuntime when both a configured RSS provider and trusted owner-scoped correlator are present. It starts immediately, polls at a bounded interval, records redacted status, and participates in shutdown/failed-startup lock handling.
- [ ] Verify hosted worker supervision across host restart/deployment replacement, backup retention, off-host copies and an actual operational restore drill.
- [ ] Configure production identity, session/token policy, TLS, CORS/CSRF where applicable, rate limits, secret rotation and KMS/envelope encryption.
- [ ] Verify no hidden order or money-movement route is exposed by the read-only assistant or analysis modules.
- [ ] Publish a production readiness report distinguishing implemented, configured, connected, live-tested and production-validated.

## Front 2 — Broker/provider integrations and real-time cycles

- [x] Implement tenant/subject/account-scoped provider sessions, per-account candle-close subscriptions, bounded concurrent analysis workers, result history, idempotency and signal expiry in code.
- [x] Implement MT5 relay onboarding with hashed one-time token storage, per-connection routes, DEMO-only first-batch binding and account identity checks in code.
- [x] Implement TradingView tenant-scoped webhook secrets, replay protection and alert history in code; TradingView remains an alert-event channel, not a continuous candle feed.
- [x] Implement cTrader read-only OAuth orchestration, accounts-scope enforcement, encrypted-token vault contract, DEMO-account selection, live spot/trendbar stream handling, closed-candle analysis binding and fail-closed reconnect paths in code.
- [ ] Validate MT5 relay on an actual DEMO terminal, including local agent install, account binding, HTTPS secret, replay protection, freshness, candle continuity, reconnect and server receipt.
- [ ] Validate cTrader OAuth with a real Spotware app and DEMO account, production KMS-backed token storage/refresh/revocation, real handshake, streaming quotes and closed trendbars.
- [x] Add M10 signal lifecycle/expiry regression coverage alongside M1, M5 and M15.
- [x] Add provider-clock boundary calculation and an injectable account-scoped clock hook. Intraday cycles can use provider timestamps; stored/compared candle-open timestamps normalize to UTC. Regression tests cover UTC+3 provider time and M1/M5/M10 boundaries.
- [x] Fail closed for D1/W1 in both single-provider and tenant/account monitors unless a verified provider session-calendar callback returns the exact last closed candle-open time. The single-provider monitor exposes `D1_W1_FAIL_CLOSED` readiness and records `DATA_UNAVAILABLE` without terminating the worker.
- [ ] Wire authenticated MT5/cTrader provider clocks and verified session-calendar callbacks to real adapters; verify DST, holidays, early closes, weekend reopen and candle timestamps against DEMO accounts. The new callback contracts are injectable but are not yet connected to live broker session calendars.
- [ ] Test M1, M5, M10 and every interval shown in the app against each provider's actual symbol catalogue and session rules; parser support alone is not evidence.
- [ ] Verify cycle timing, candle-close boundaries, latency, expiry, provider outage, reconnect, process restart and notification deduplication against real provider sessions.
- [x] Keep D1/W1 fail-closed until verified provider session calendars and next-session boundaries are wired into analysis; do not substitute UTC midnight/Monday boundaries.
- [ ] Document provider-specific unsupported symbols/intervals instead of promising universal compatibility.

## Front 3 — Intelligence, news, modules, notifications and interface wiring

- [x] Implement conservative news headline triage with source provenance, timestamps, source allowlisting, macro relevance matching and affected-asset mapping. Classification does not infer sentiment, direction or probability.
- [x] Wire the source-aware evidence correlator into EcosystemService news responses. StandaloneRuntime accepts an optional correlator, verifies that its SQLite store is scoped to the configured local tenant/subject and resides at the backup-covered `news-evidence.sqlite3` path, and exposes evidence processing through the existing Análise response. Host source-policy provisioning and Lovable acceptance remain open.
- [x] Add `NewsPollingWorker` to poll up to 50 configured RSS headlines at a bounded interval (default 60 seconds, minimum 30), persist through the trusted correlator, isolate item-level errors and expose local readiness. It never fetches full articles or confirms facts automatically; if the provider reports stale/unavailable, the worker skips ingestion rather than persisting old headlines.
- [x] Add source-aware news evidence clustering: trusted publisher identity/tier/hosts, HTTPS URLs, aware timestamps, same-publisher duplicate suppression and cross-publisher review candidates marked `UNVERIFIED_REPORT`. The owner-scoped append-only SQLite store persists across restarts; source independence, article truth and market direction are never inferred. Multi-replica storage and screen-by-screen frontend acceptance remain open.
- [x] Add strict economic-calendar event normalization with publisher-scoped IDs and source tier bound from trusted host configuration (never from provider payload), HTTPS provenance, timezone-aware scheduled/observed timestamps, explicit impact/status, actual/consensus/previous/revised-previous fields, strict type validation, duplicate-ID rejection, and HTTPS source-host enforcement against an allowlist supplied by trusted host configuration. Provider payloads cannot choose their own publisher identity, trust tier or arbitrary provenance domain. Missing values remain null; cross-source fingerprints are candidates only and never auto-merge events.
- [x] Add an injectable economic-calendar ingestion service and append-only SQLite observation store. It applies trusted publisher identity/tier/host policy, preserves publisher event identity, makes repeated observations idempotent, stores revisions separately and never invents absent values.
- [x] Add `EconomicCalendarPollingWorker` for host-injected fetchers registered under trusted source IDs. It isolates source failures, records redacted source status, runs immediately and on a bounded interval, and has start/stop/status lifecycle. StandaloneRuntime can start/stop it and keeps the SQLite process lock while it is active.
- [x] Wire read-only calendar retrieval into the existing Análise area through its existing route contract; missing storage returns NOT_CONFIGURED, and stored observations are explicitly not labelled live or freshly updated. No new visible area or UI redesign was added.
- [ ] Supply and validate official primary-source calendar adapters (for example central banks and statistical agencies), wire their source policies/fetchers into the polling worker, and run the worker under hosted supervision. The worker is an adapter scheduler, not an official feed implementation. Move observations to the shared production database before multi-replica use.
- [ ] Expand news beyond headline triage: article verification, duplicate clustering, independent-source corroboration and conflicting-report handling.
- [ ] Add a structured economic-calendar ingestion pipeline from official primary sources, with timezone, release time, actual/consensus/previous values, revisions, impact and source links. Do not invent missing consensus or release data.
- [ ] Build event-to-asset context and cross-market relationships; do not infer price direction from keyword matches or a single headline.
- [ ] Keep all existing module inventory and map every item to one of the six approved areas or internal infrastructure; record owner-facing behavior and API route.
- [ ] Connect existing Lovable controls to real API contracts without changing appearance; complete screen-by-screen network acceptance and error/empty/stale/loading states.
- [ ] Complete adversarial synthesis: supporting evidence, counterevidence, source conflicts, missing evidence, alternative explanations and explicit abstention.
- [ ] Keep probability unavailable until representative out-of-sample outcomes, calibration diagnostics and drift gates pass; an evidence score is not a win probability.
- [ ] Version rules/models and retain provenance, forecasts, corrections and outcomes; evaluate changes out of sample and make them reversible.
- [x] Implement Web Push building blocks in code: tenant-scoped registration/list/revocation routes with host callbacks, endpoint host allowlisting, AES-GCM subscription-store adapter over an injected durable tenant backend, injected VAPID sender, and tenant notification sink/outbox components.
- [ ] Complete production Web Push activation: sender-side DNS/IP validation and pinning, redirect suppression, deployed durable backend/KMS and VAPID secrets, verified identity/CSRF callbacks, hosted worker wiring, delivery/retry/dead-letter telemetry, and Android/iOS tests with the app/browser closed. RSS redirect suppression does not satisfy the Web Push sender requirement.
- [ ] Ensure market, calendar, notification and backup workers run under hosted supervision when the user's PC/app is closed; local process threads do not provide always-on operation.
- [ ] Verify Reserva Fiscal Brazil and Exterior queues, persistence, identity/ownership, reconciliation and recovery; verify assistant remains strictly read-only.
- [ ] Verify the minimal/secret mode shows only the intended signal and evidence score without changing the main interface or inventing probabilities.

## Modules explicitly retained and integrated in this continuation

The following recently added modules are part of the same application foundation; none is a new visible navigation area:

- `analysis/news_event_intelligence.py` — conservative headline event/category and affected-asset triage only; no sentiment, direction or probability.
- `analysis/news_evidence_corroboration.py` — trusted publisher provenance, duplicate suppression and cross-publisher review candidates; candidate matches remain unverified.
- `integration/rss_news_provider.py` — configured RSS/Atom ingestion; feed and article destinations are allowlisted, redirects are rejected by the default HTTP client, HTTPS ports/timeouts are bounded. DNS/IP pinning is not yet implemented.
- `EconomicCalendarPollingWorker` — host-injected trusted-source polling with per-source status, failure isolation, and StandaloneRuntime lifecycle integration; official publisher adapters remain host-supplied.
- `NewsPollingWorker` — bounded RSS headline polling and owner-scoped evidence ingestion, started/stopped by StandaloneRuntime when both trusted correlator and configured RSS provider exist; hosted supervision and source policies remain deployment requirements.
- `SQLiteNewsEvidenceStore` and `SQLiteEconomicCalendarStore` — owner-scoped news evidence and publisher-scoped calendar observations, both covered by local backup/readiness checks when stored at the documented runtime paths.
- `analysis/economic_calendar.py` and `integration/economic_calendar_ingestion.py` — strict publisher-scoped event normalization, revision history and append-only local observations; official feed adapters and hosted scheduling are still pending.
- `data/provider_clock.py` — provider-time candle boundary calculations for supported intervals; actual authenticated provider clock wiring remains pending.
- `core/unified_intelligence.py` — one shared intelligence coordinator across the six areas; the eight research-grade intelligence layers remain an acceptance target, not a claim of ASI/AGI.
- `core/sqlite_backup_service.py` and `core/sqlite_backup_scheduler.py` — local backup/isolated restore primitives; off-host backup and hosted scheduling remain release gates.
- Web Push components — tenant registry/routes, encrypted PostgreSQL adapter contract, VAPID sender and tenant outbox/sink. They remain disabled until sender DNS/IP pinning, redirect suppression, real KMS/secrets, hosted worker and device acceptance are proven.

## Advanced intelligence acceptance

The target is research-grade, ASI-inspired engineering, not a claim of actual ASI/AGI or infallibility. Completion requires measurable source integrity, independent evidence channels, temporal context, cross-asset context, adversarial synthesis, calibrated forecast evaluation, persistent versioned learning, drift monitoring, explanations and safe abstention. Intelligence must never grant itself execution authority.

## Current verification boundary

- Active integration PR: [#534](https://github.com/tradekemily06-bit/Controlador-trade/pull/534), branch `fix/six-visible-areas-memory-capability`, base #533. PR is open, draft and unmerged. The #532 sibling's relevant readiness changes are reconciled here; do not merge #532 separately.
- Current tested code head: `fc832dc469378dd0383ffaf9bad528612ead0d2b`.
- CI run [46117473484](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46117473484): the CI job, full test job and Windows PowerShell validation passed on this exact code head. P1.9, full suite, dependency audit, Python compilation, production and analyst container builds/health smokes all passed. Required commit-status publication was queued and Semgrep was still running at the time of this update.
- Backup/readiness inventory now matches for all 18 SQLite database IDs. Runtime-created database paths all map to a backup and readiness entry; optional forecast audit, security audit, signal evidence, news evidence, calendar and cTrader/legacy stores are explicitly non-fatal when absent.
- D1/W1 guard prevents UTC fallback in both monitor paths. Real MT5/cTrader session calendars and provider clock callbacks remain unconnected and must be verified against DEMO provider evidence.
- RSS security hardening rejects redirects in the default client, non-standard HTTPS ports, credentials/fragments, unbounded/non-finite timeouts and article links outside trusted publisher hosts. DNS/IP pinning and DNS-rebinding protection remain open. This RSS change does not prove Web Push sender redirect/DNS safety.
- Economic-calendar and news polling workers are process-lifetime workers. Official primary-source calendar adapters, trusted news source policies, hosted supervision and deployment-level continuity remain unconfigured.
- News polling does not persist headlines when the RSS provider reports stale/unavailable; evidence ingestion requires a configured provider and trusted correlator. The worker does not fetch full articles or confirm facts.
- News evidence and calendar observations use local SQLite in this runtime path. They remain single-host/single-runtime, not production shared multi-tenant storage.
- Live MT5/cTrader handshakes, each provider's actual symbol/timeframe catalogue, production shared DB/KMS/identity, hosted worker continuity, external push delivery with the app/browser closed, and Lovable screen-by-screen API acceptance remain unverified.
- No merge, deployment, production activation or Lovable UI modification was performed. SIMULAÇÃO remains the only enabled operating mode; REAL/order/money-movement routes remain disabled.

## Definition of done

Nothing is closed merely by being listed or implemented. Each checkbox needs a linked code change, automated tests, integration evidence, operational evidence where relevant, and a clear status. Release requires the combined PR chain, no dropped #532 changes, all three fronts accepted, all six areas connected without visual changes, live data and notifications demonstrated, security/restore checks passed, and owner acceptance.


## CI confirmation — exact PR tip, 28 November 2026

- GitHub Actions run [46117623610](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46117623610) completed successfully for PR tip `1980b696b6e2780a27aa5be064cc34fbb88454c7`.
- All four workflow jobs passed: P1.9 robustness + full test suite + dependency audit + Python compilation + production/analyst container builds and health smokes; Windows PowerShell validation; protected-branch compatibility; required commit-status publication.
- This closes the previously pending CI confirmation for the current PR tip. It does not prove live broker sessions, official calendar adapters, shared production storage/KMS, hosted worker continuity, real-device push delivery, or Lovable end-to-end acceptance.
- PR #534 remains draft, open and unmerged. No deployment, REAL activation, order route, or frontend change was performed.


## Three-front continuation — 28 November 2026

### Analysis and intelligence
- NewsPollingWorker no longer advances `last_success_at` when one or more returned items fail URL validation or evidence ingestion. A partially processed poll remains `PARTIAL` and does not mask a degraded evidence pipeline as fully successful.
- Added regression coverage for partial rejection and for a valid empty live poll.

### Connections and market data
- MarketDataProviderRegistry now supports a host-configured provider heartbeat freshness window (1–3600 seconds) and future-clock tolerance (0–30 seconds), with finite-number and boolean rejection.
- The default remains 30 seconds of heartbeat age and 5 seconds of future tolerance. Deployments can match the threshold to a provider's actual heartbeat cadence rather than falsely marking a slower but healthy adapter stale.
- Added tests for a 45-second heartbeat under a 60-second configured threshold and invalid configuration values. This changes connection health classification only; it does not establish a broker handshake or market-data feed.

### Notifications and infrastructure
- NotificationOutboxWorker now rejects booleans, NaN, infinity and out-of-range poll intervals; accepted interval is 0.1–3600 seconds.
- Stop timeout is now validated as a finite value from 0–60 seconds, preventing malformed runtime configuration from crashing the worker shutdown path.
- Added regression tests for both timing boundaries.

### Validation boundary
- Code commits: `1dcb0693` (news success semantics), `8004fb29` (notification timing validation), `642cfa01` (provider heartbeat configuration), `112b219e` (provider tests), `4b6858d3` (worker hardening tests).
- Current code head: `4b6858d3b2acacff4140a47c1167a426a0937156`.
- At the time of this update, GitHub has not exposed a CI workflow run or commit status for this exact head. These changes are committed but must not be described as CI-validated until the full pipeline runs and passes.
- No live provider test, production deployment, hosted worker continuity, push delivery, Lovable UI modification, merge, or REAL/order enablement was performed.
