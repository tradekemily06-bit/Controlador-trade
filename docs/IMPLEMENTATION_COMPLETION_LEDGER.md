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
- [x] Add a tenant/subject-scoped immutable strategy-trial ledger in the existing backed-up signal-evidence SQLite database. It records selection trials, dataset SHA-256 fingerprints, strategy versions, evaluation windows, timestamps and scalar diagnostics; supports idempotent retries and deterministic SHA-256 record identifiers.
- [x] Enforce a single chronological holdout evaluation per experiment: a holdout requires prior selection trials, must use a different dataset fingerprint, must start strictly after every selection window, and freezes further selection. The ledger is exposed as an internal Estudo operation using only the trusted runtime tenant identity.
- [x] Add an Estudo operation that runs the existing `HistoricalValidationEngine` over validated chronological OHLCV candles, computes realized backtest diagnostics, fingerprints the exact candle payload and persists selection/holdout metrics in the tenant-scoped ledger. Integration tests verify the six-area dispatcher, trusted host-injected tenant identity, tenant isolation and fail-closed behavior when identity is absent. The decision stream is still caller-supplied and explicitly labelled unverified; this does not yet prove that decisions were generated by a versioned strategy implementation.
- [ ] Connect the evaluator to immutable provider candle snapshots and versioned in-repository strategy functions; add `evaluate_strategy_robustness` outputs, effective-trial-count derivation and complete selection/holdout/backup-restore acceptance. Do not accept a caller-supplied decision stream as proof of strategy quality.
- [ ] Add a complete Estudo workflow/API acceptance test covering selection, holdout, diagnostics, tenant isolation, backup/restore and frontend contract without changing the Lovable interface.
- [ ] Keep all existing module inventory and map every item to one of the six approved areas or internal infrastructure; record owner-facing behavior and API route.
- [ ] Connect existing Lovable controls to real API contracts without changing appearance; complete screen-by-screen network acceptance and error/empty/stale/loading states.
- [ ] Complete adversarial synthesis: supporting evidence, counterevidence, source conflicts, missing evidence, alternative explanations and explicit abstention.
- [ ] Keep probability unavailable until representative out-of-sample outcomes, calibration diagnostics and drift gates pass; an evidence score is not a win probability.
- [ ] Version rules/models and retain provenance, forecasts, corrections and outcomes; evaluate changes out of sample and make them reversible.
- [x] Implement Web Push building blocks in code: tenant-scoped registration/list/revocation routes with host callbacks, endpoint host allowlisting, AES-GCM subscription-store adapter over an injected durable tenant backend, injected VAPID sender, and tenant notification sink/outbox components.
- [ ] Complete production Web Push activation: sender-side DNS/IP validation and pinning, redirect suppression, deployed durable backend/KMS and VAPID secrets, verified identity/CSRF callbacks, hosted worker wiring, delivery/retry/dead-letter telemetry, and Android/iOS tests with the app/browser closed. RSS feed DNS/IP pinning and redirect suppression are implemented separately; they do not satisfy the Web Push sender requirement.
- [ ] Ensure market, calendar, notification and backup workers run under hosted supervision when the user's PC/app is closed; local process threads do not provide always-on operation.
- [ ] Verify Reserva Fiscal Brazil and Exterior queues, persistence, identity/ownership, reconciliation and recovery; verify assistant remains strictly read-only.
- [ ] Verify the minimal/secret mode shows only the intended signal and evidence score without changing the main interface or inventing probabilities.

## Modules explicitly retained and integrated in this continuation

The following recently added modules are part of the same application foundation; none is a new visible navigation area:

- `analysis/news_event_intelligence.py` — conservative headline event/category and affected-asset triage only; no sentiment, direction or probability.
- `analysis/news_evidence_corroboration.py` — trusted publisher provenance, duplicate suppression and cross-publisher review candidates; candidate matches remain unverified.
- `integration/rss_news_provider.py` — configured RSS/Atom ingestion; feed and article destinations are allowlisted, redirects are rejected, HTTPS ports/timeouts are bounded, DNS answers are checked for public routability and the HTTPS socket is pinned to the validated IP while TLS SNI/hostname verification retains the configured publisher host.
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


## Follow-up continuation — 28 November 2026

### CI regression correction
- The full-suite run [46157811935](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46157811935) exposed three legacy notification-worker tests that intentionally use 10–50 ms polling intervals. The new lower bound of 100 ms rejected those supported test/runtime intervals; 2,541 tests and 44 subtests passed, with exactly these three failures.
- Restored compatibility by setting the finite notification polling interval range to 0.01–3600 seconds. Invalid values still reject booleans, NaN, infinity, zero, values below 0.01 and values above 3600. The stop timeout remains finite and bounded at 0–60 seconds.
- Updated the hardening regression test to reject 0.001 seconds rather than 0.01 seconds. The fix is committed; it is not marked CI-passed until the new workflow run completes.

### News evidence independence
- Added a trusted `publisher_group` field to `NewsSourcePolicy`. Feed IDs and hostnames alone do not establish independent editorial sources; the host can now group syndication aliases and related feeds under one publisher identity.
- Cross-publisher review candidates are now created only when the two configured source policies belong to different publisher groups. If a prior source is no longer in the trusted policy set, it is not treated as corroboration.
- Added a regression test proving that two feed IDs from the same configured publisher group do not count as independent corroboration.
- This remains headline-level candidate matching, not article verification or proof of independent reporting. Full article retrieval, factual claim extraction, contradiction analysis and provenance-aware source lineage remain open.

### Validation status
- New commits after the previous ledger update: notification interval compatibility fix, test adjustment, publisher-group corroboration guard and regression test.
- Full CI has not yet reported a result for the latest branch tip. Do not mark these changes as validated until the complete workflow passes.
- No live broker session, hosted worker, shared production database, KMS, real push delivery, Lovable acceptance, merge or deployment was performed. SIMULAÇÃO remains the only enabled mode; REAL, order submission and money movement remain disabled.


### CI completion confirmation — 28 November 2026
- The corrected head `613a9c06bee085fe4c4bf2105665c8c906e2af4c` completed GitHub Actions run [46159301464](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46159301464) with conclusion SUCCESS.
- Confirmed successful steps: P1.9 robustness tests, full test suite, dependency security audit, Python surface compilation, production container build and health smoke test, standalone analyst container build and health smoke test, Windows PowerShell validation, protected-branch compatibility check, and required commit-status publication.
- This supersedes the earlier statement that CI was still pending for this head. It validates repository tests/builds only; it does not replace live-provider, production infrastructure, hosted-worker, push-device, or Lovable end-to-end acceptance.


### RSS transport SSRF hardening — 28 November 2026
- The default RSS/Atom HTTP transport now resolves each configured publisher hostname, rejects empty, invalid, private, loopback, link-local, reserved, or mixed public/private DNS answer sets, and connects to one of the validated public IPs without performing a second DNS lookup in the HTTPS connection.
- TLS certificate validation and SNI continue to use the original configured hostname while the TCP socket is pinned to the validated IP. Redirects remain rejected; response size, status, content length, timeout and HTTPS port remain bounded.
- Added tests for public IPv4/IPv6 answers, duplicate address normalization, private/mixed DNS rejection, DNS failures, and verifying that the TCP connection uses the pinned IP while TLS uses the original hostname.
- The injectable opener remains a test seam; production default transport uses the pinned HTTPS implementation. This does not provide article-body retrieval, publisher fact verification, or Web Push sender DNS pinning.
- Latest code changes require the full CI workflow to pass before this hardening is marked validated.


### Confirmed CI and calendar-worker lifecycle hardening — 28 November 2026
- GitHub Actions run [46159719444](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46159719444), run 8803, completed with overall SUCCESS on head `80d5f9b6ff6e24f780d53bcd008413ef37b95485`. All jobs passed: P1.9 robustness, full test suite, dependency audit, Python compilation, production and analyst container builds/health smoke tests, Windows PowerShell validation, protected-branch compatibility, and required status publication.
- Added finite/bounded shutdown-timeout validation to `EconomicCalendarPollingWorker.stop()`, aligned with the notification worker lifecycle contract. Invalid bool/NaN/infinity/negative/over-60s values now fail explicitly; zero timeout remains valid. Added parameterized regression coverage.
- The calendar-worker change and its tests were committed after run 8803; therefore they require a fresh CI run on the exact new head and are not yet marked validated.
- Calendar date-only event precision remains an explicit foundation gap: the current normalizer requires a timezone-aware scheduled timestamp. It must not fabricate midnight for official sources that publish only a date. The schema/API migration is not silently considered complete.


### Economic calendar date-only precision — 28 November 2026
- Added explicit `CalendarTimePrecision.EXACT` and `DATE_ONLY` semantics. A date-only official event stores `scheduled_date` and a null `scheduled_at`; the normalizer rejects timestamp-shaped date-only values and never fabricates midnight.
- Preserved existing exact timestamp behavior and timezone normalization.
- Extended the local SQLite observation schema with `scheduled_date`, including an additive migration for existing databases. Date-only observations can be queried by their calendar date; exact events remain filtered by their timestamp.
- Added normalization, persistence, and legacy-schema migration regression tests.
- CI runs for intermediate commits show the targeted robustness tests and/or full suite passing, but this ledger entry is NOT considered validated until the full CI run for the final branch head completes successfully.
- Limitation remains: date-only filtering uses the calendar-date portion of the requested UTC range. Provider-specific local calendar zones and official calendar adapters still need explicit configuration and validation before production use.


### cTrader standalone provider registration seam — 28 November 2026
- The standalone market-data provider factory now accepts an explicit host-injected `ctrader_adapter_factory` for the existing `CTraderReadOnlyMarketDataAdapter`. The `ctrader_demo` provider cannot be selected without that trusted factory; it does not create credentials, OAuth clients, transports, or pretend a connection is active.
- Added tests for fail-closed behavior without the host factory and type-checked adapter registration when the host supplies it.
- This is a registration seam only. The production OAuth/KMS configuration, official Open API transport, DEMO account handshake, provider session validation, and live candle/quote tests remain separate release gates.
- CI for the provider-factory commit is running; no pass is claimed until the exact final head completes.


### CI confirmation — cTrader provider registration seam (28 November 2026)
- GitHub Actions run [46160647350](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46160647350) completed with overall SUCCESS on code head `593af4f4fa00846afa11b0ba4972ade5d5cc995d`.
- All four workflow jobs passed: P1.9 robustness tests (17 passed), full test suite (2,567 passed and 44 subtests passed), dependency security audit, Python compilation, production and analyst container builds/health checks, Windows PowerShell validation, protected-branch compatibility and required commit-status publication.
- This validates the date-only economic-calendar precision work, worker lifecycle hardening, RSS pinned-transport hardening, cTrader provider-factory seam and associated regression tests present in that code head. It does not validate a real cTrader OAuth login, DEMO account handshake, live quotes/candles, official calendar publisher adapters, hosted scheduling, shared PostgreSQL/KMS, Web Push closed-app delivery, or Lovable end-to-end wiring.
- PR #534 remains open, draft and unmerged. No deployment, frontend modification, REAL activation, order submission or money movement was performed.


### cTrader application-dispatcher visibility — review correction (28 November 2026)
- The previous review correctly observed that `StandaloneRuntime` does not pass its tenant provider registries/account services into `build_standalone_application`; the six-area dispatcher's generic Central handler therefore does not itself render owner-scoped provider sessions.
- That observation was incorrectly described as a missing HTTP integration. Inspection of `standalone_app.py` confirms dedicated tenant-scoped HTTP endpoints already exist for cTrader OAuth provisioning/callback, DEMO account listing and selection, provider connection status, session health, reconnect, and disconnect/revocation. These routes resolve `TenantContext` from the trusted WSGI identity boundary rather than accepting tenant IDs from browser payloads.
- Accordingly, this is a separation between the six-area generic dispatcher and the dedicated provider API, not proof that the cTrader API routes are absent. Do not add duplicate routes or pass raw tenant identifiers through the area dispatcher. The remaining question is whether the standalone host actually injects the OAuth/KMS/transport dependencies required to activate those routes in a deployment.


### Standalone container and production entrypoints — review correction (28 November 2026)
- The previous review inspected only the root `Dockerfile` and `app.py` and incorrectly concluded that the independent standalone service lacked its own container entrypoint.
- The repository also contains `Dockerfile.standalone`, whose command is `python standalone_app.py`. The CI workflow explicitly builds this image and runs its health smoke test with `CONTROLADOR_SINGLE_USER_IDENTITY=ci-owner`; `standalone_app.py` constructs `StandaloneRuntime`, serves `StandaloneWSGIApplication`, and closes the runtime on shutdown.
- The root `Dockerfile` and `app.py` remain the legacy operational service. They are a separate image/entrypoint and must not be confused with the standalone analyst container.
- Therefore, the existence and basic startup of the standalone container ARE covered by CI. The remaining release gates are real host dependency injection, remote identity middleware, production deployment/provisioning, live provider sessions, persistent shared infrastructure and external end-to-end acceptance. No entrypoint replacement is needed based on this finding.


### Standalone host dependency activation — review correction (28 November 2026)
- The standalone host bootstrap contract is already implemented in `standalone_app.py` through the operator-controlled `CONTROLADOR_STANDALONE_RUNTIME_FACTORY=module:function` setting. The configured module is imported only during server startup; request payloads cannot select or alter the factory.
- The bootstrap validates the module/function syntax, requires a callable factory, wraps import/factory failures without silently falling back, and accepts only an active `StandaloneRuntime`. Invalid return values are closed when possible and startup is aborted.
- `tests/test_standalone_app.py` covers default startup when no factory is configured, successful loading of an injected trusted factory, malformed factory specification, invalid return type, and runtime cleanup when application/server startup fails.
- This resolves the previously listed missing-bootstrap implementation item. It does NOT provision any real credentials, KMS, provider transport, notification sink, calendar/news source adapter, hosted worker, or shared database. The operator must still deploy a trusted module that injects those dependencies from secret management and trusted configuration. The default container remains intentionally fail-closed/unconfigured for optional integrations; health checks do not prove live provider or push delivery.


### CI confirmation — security-mode correction (28 November 2026)
- GitHub Actions run [46163779461](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46163779461) completed with conclusion SUCCESS for commit `7c8ba480195b3880df0660f75bafafb03623bbb6`.
- This validates the repository workflow for the REAL-mode authorization correction and its current branch contents. It does not prove live broker connections, production secrets/KMS, hosted worker continuity, external push delivery, or Lovable end-to-end acceptance.


### News evidence integration hardening — 28 November 2026
- Fixed the production source-identity seam: the polling worker now asks the trusted corroborator to resolve an article URL to exactly one configured source_id policy, rather than passing the URL hostname as if it were the policy identifier. Unknown or ambiguous publisher mappings fail closed; test doubles without the resolver retain their generic host-key behavior.
- Exposed the corroborator's configured persistence adapter through a read-only store property. This allows StandaloneRuntime's existing tenant/subject and backup-path checks to actually inspect the injected news evidence store; previously the runtime looked for store while the correlator only held _store, silently skipping those boundary checks.
- Added regression coverage for publisher resolution, ambiguous/unknown domains, worker use of configured publisher IDs, and runtime-visible store identity. GitHub Actions for the latest branch head are pending; these changes are not marked validated until CI completes.

## Selective intelligence reuse — 28 November 2026
- [x] Review OpenTerminalUI's research-autopilot and multi-agent-debate patterns against existing Controlador-trade capabilities. Multi-agent debate is not copied because `IntegratedMarketReader` and `SeniorMarketReasoner` already preserve independent domains, supporting/contradicting evidence, conflicts and reassessment; a second orchestrator would duplicate logic and introduce LLM cost/provider requirements.
- [x] Add an independent Python-standard-library strategy robustness scorecard inspired by OpenTerminalUI's MIT-licensed research-validation approach: untouched out-of-sample-only input, at least 30 completed trades and 60 periods, explicit costs-included flag, aligned benchmark, second run with declared >=2x costs, trial-count correction (PSR/DSR), moving-block bootstrap and rolling-window stability. Degenerate variance abstains instead of manufacturing confidence. `analysis/strategy_robustness.py`; regression tests in `analysis/test_strategy_robustness.py`.
- [ ] CI validation is pending for the new robustness implementation. It is not yet wired into a live backtest/Estudo API, and no strategy can be promoted by this scorecard. `ROBUST_REQUIRES_REVIEW` is diagnostic only, not a profitability probability or execution authorization.
- [x] Review OpenTraderWorld FSL-1.1-MIT terms. No code copied because the current license restricts competing commercial use; only independently implemented engineering principles may be adopted. See `docs/INTELLIGENCE_REUSE_REVIEW.md`.

## Statistical formula correction — 28 November 2026
- [x] Correct the PSR denominator to use the non-excess kurtosis convention required by Bailey–López de Prado; the implementation stores excess kurtosis and converts it explicitly in the formula.
- [x] Correct DSR trial correction to use cross-sectional variance of the selection-period Sharpe ratios for every strategy trial, rather than reusing the selected strategy's time-series Sharpe-estimation variance. The API now requires exactly one finite selection-period Sharpe per declared trial and abstains when the trial record is incomplete.
- [x] Add regression tests for Gaussian-kurtosis convention, DSR trial-dispersion calculation, missing/incomplete trial records and trial-count consistency.
- [ ] Re-run CI after the formula correction and integrate the scorecard with a real backtest trial ledger. The selection-period trial Sharpe inputs must be retained by the backtest engine; never reconstruct or invent discarded trials.

## CSCV backtest-overfitting diagnostic — 28 November 2026
- [x] Add an independent standard-library CSCV/PBO diagnostic over a chronological period-by-strategy return matrix. It evaluates all half-block combinations for 8–16 even contiguous blocks, reports PBO, selected-winner out-of-sample loss frequency, OOS Sharpe summaries and selection frequency. Zero-variance strategies receive a conservative zero Sharpe; invalid/ragged matrices are rejected.
- [x] Add regression tests for combinatorial split counts, tie behavior, selection-frequency accounting, invalid matrices and unsupported block counts.
- [ ] Integrate only after the backtest engine records every attempted strategy variant and its full time-aligned return series, preserves chronological holdout, and records actual transaction costs. The current backtest engine does not yet provide that evidence; PBO remains an isolated diagnostic and must not be presented as a live feature.

## Selection-versus-holdout separation — 28 November 2026
- [x] Separate the selection-period return sample from the untouched out-of-sample holdout. DSR is now computed only from the selected variant's selection-period returns and the cross-sectional Sharpe ratios of all recorded variants; PSR, bootstrap and rolling stability use the distinct OOS sample and aligned benchmark.
- [x] Require the selected variant index to be the selection-period Sharpe winner and verify its supplied trial Sharpe matches the selected returns at the same unannualized frequency. Missing, inconsistent or insufficient selection records fail closed.
- [ ] The current backtest engine does not yet produce separate immutable selection/holdout datasets or retain every trial's same-window Sharpe. Do not call the robustness workflow complete until this data lineage and cost model are integrated.

## Effective-trial correction and bounded CSCV — 28 November 2026
- [x] Separate recorded strategy variants from the effective number of independent trials used by DSR. The caller must supply `effective_num_trials` from a defensible correlation-aware estimate, bounded by the recorded trial count; the scorecard no longer silently assumes every parameter variant is independent.
- [x] Optimize CSCV by pre-aggregating centered block moments, reducing per-split work to block/strategy aggregates rather than rescanning every period. Bound the input matrix to 2,000,000 cells and retain exact combinatorial split accounting.
- [ ] Validate effective-trial estimation against the actual backtest search space; until then DSR must be presented with its independence assumption and uncertainty, not as a calibrated probability.

## Strategy robustness CI confirmation and integration boundary — 28 November 2026
- [x] GitHub Actions run [46167329702](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46167329702) completed SUCCESS for code head `b8d7046943287cedb1b424f9c0b93f3fd34ae599`; run [46167303712](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46167303712) also completed SUCCESS for the preceding CSCV precision correction.
- [x] The latest tested head includes the CSCV out-of-sample mean precision correction and bounded-memory aggregation optimization in `analysis/strategy_robustness.py`.
- [ ] The robustness diagnostics remain research components, not a live Estudo feature. The current `BacktestEngine` emits individual backtest results but does not persist every attempted parameter/strategy variant as a complete, time-aligned return matrix, nor immutable selection/holdout partitions and trial-count provenance. Do not claim an integrated anti-overfitting workflow until that data contract, durable tenant-scoped trial ledger, API exposure and Estudo consumption are implemented and tested.
- [ ] Effective-trial count is still supplied by the caller; correlation-aware estimation from the recorded strategy search space is not yet implemented. Keep the DSR limitation visible.
- [ ] No production database, real provider feed, live backtest execution, or Lovable end-to-end test is implied by CI success. PR #534 remains draft/open/unmerged; no deployment or REAL execution authorization.



## Trusted global news source bootstrap — 28 Nov 2026

- Added `integration/news_source_configuration.py` to build the news evidence correlator from explicit host-controlled `CONTROLADOR_NEWS_SOURCE_POLICIES` JSON. Publisher identity and trust tier are never accepted from RSS payloads.
- Wired this builder into `StandaloneRuntime` when a trusted correlator was not injected. When configured, the runtime creates/initializes the owner-scoped `news-evidence.sqlite3` store inside the runtime backup directory; the existing RSS polling worker can then start when feed URLs are configured too.
- Rejects malformed policy JSON, unsupported fields/tiers, duplicate source IDs, duplicate hosts and overlapping parent/subdomain trust scopes. Missing policy keeps evidence polling disabled; no implicit trust fallback.
- Added regression tests for disabled-by-default behavior, owner-scoped persistence, trusted host resolution and malformed/ambiguous policy rejection.
- Added `docs/NEWS_SOURCE_CONFIGURATION.md` with configuration schema, starter official Federal Reserve/ECB feed URLs, polling limits, source-trust rules and explicit limitations.
- Latest implementation commits: `292254c1` (builder), `abe79e15` (runtime wiring), `618f6df5` (tests), `1ff8e7c9` (overlap rejection), `0711fb33` (configuration guide).
- At ledger update time GitHub had not yet exposed a workflow run or commit status for exact latest head `0711fb3319c5312df66263c80221c8f331026c05`; this increment is **not yet CI-validated**.
- This does not mean news is live by default: operators must configure approved RSS feed URLs and the matching trusted publisher policies. Current ingestion remains headline-level; full-article retrieval/claim extraction, official global calendar adapters, hosted worker continuity, shared production DB/KMS and Lovable end-to-end acceptance remain open. No live feed, real device or hosted deployment was tested.


## News polling-to-application read path — 28 Nov 2026

- `NewsPollingWorker` now retains the last provider batch in memory and exposes it through `latest_items()`; reading news in the app does not trigger another RSS network poll when the standalone worker is attached.
- `StandaloneRuntime` attaches its worker to `EcosystemService` after startup. The Analysis/news handler reads the worker's cached batch and the corroborator's already-persisted evidence records.
- Removed evidence ingestion side effects from `EcosystemService.news_status()`. The background worker is the sole ingestion path; the API no longer attempts to identify a publisher by raw hostname or writes evidence during a user read.
- Added symbol matching against exact tickers, currency-pair components and headline-classified asset aliases (including XAU/GOLD and XAG/SILVER).
- Response now exposes worker collection state, persisted evidence, and explicit item freshness (`CURRENT`, `STALE`, `NO_DATA`). Partial collection is not reported as live.
- Added tests for worker cache exposure, API reads without another provider fetch, persisted evidence reads without duplicate ingestion, and partial collection freshness.
- Latest implementation commits: `746cfaa3`, `36814182`, `3bffba48`, `93536576`, `1e574324`, `a630682d`, `fe7cde79`, `051f6752`.
- CI status for this new increment has not yet been returned by GitHub; it is **not marked CI-validated**.
- The cache is process-local and represents the most recent bounded poll batch, not a durable complete news archive. The evidence store remains SQLite/single-runtime; hosted continuous collection, cross-replica shared storage, full article retrieval/claim extraction and live external feed acceptance remain release gates.


## High-impact news notifications — 28 Nov 2026

- Added an optional evidence callback to `NewsPollingWorker`. It runs only after a new evidence record is persisted, only when the conservative headline classifier returns `HIGH_REVIEW`, and never for duplicate evidence.
- Standalone runtime routes these alerts through the trusted local `TenantNotificationDispatcher`, with a deterministic notification ID derived from the evidence ID. The alert says the headline is unverified and is not a price forecast or trading instruction.
- Notification callback errors are counted separately from feed/evidence ingestion errors; a failed notification does not rewrite a successfully persisted evidence cycle as an ingestion failure.
- Worker now treats partial feed coverage as `PARTIAL`, not healthy. A successful response from only some configured feeds no longer advances the full-cycle success timestamp.
- Added tests for high-impact alert emission, duplicate/low-impact suppression, notification error isolation and partial feed coverage.
- Latest commits: `078f16ba`, `0ee2c0d7`, `f4c95b11`, `f48c1f5b`, `35a19bbf`, `59fd9aed`.
- GitHub CI has not yet returned workflow runs or status checks for this increment; these changes remain **not CI-validated**. External push delivery and mobile/browser receipt are also untested.
- Alerts are deliberately limited to `HIGH_REVIEW` headline triage to avoid flooding. They are not a confirmation of facts or a trade signal. User preferences, per-asset subscriptions and hosted multi-replica delivery remain separate work.


## News alert and evidence-memory hardening — 28 Nov 2026

- News alerting is now connected to the tenant-scoped notification dispatcher. Only newly persisted `HIGH_REVIEW` headline evidence can trigger an `IMPORTANT` market notification; evidence IDs make the notification deterministic, and duplicate/lower-review headlines are suppressed.
- Notification callback failures are reported separately from evidence ingestion state.
- Worker health now accounts for configured-feed coverage. A partial response from a multi-feed configuration remains `PARTIAL` and does not advance the full-success timestamp.
- Active evidence matching now loads only the most recent 72 hours and at most 5,000 records into memory. Older published headlines remain in the append-only tenant SQLite audit store but do not participate in recent corroboration or inflate the active matching set.
- Added regression coverage for high-impact alert gating, deduplication, callback error isolation, partial feed coverage, bounded evidence loading and stale headline exclusion from active memory.
- Latest commits: `b42e1b4f`, `dd2b1efd`, `cfa04b52`, `41639b51` (plus alert/coverage commits `078f16ba`, `0ee2c0d7`, `f4c95b11`, `f48c1f5b`, `35a19bbf`, `59fd9aed`).
- CI is still not confirmed for the final head. The earlier CI run was observed in progress before the latest hardening commits; no success is claimed for the current head.
- Disk retention/compaction for the append-only SQLite archive, shared production database, hosted worker continuity, full article analysis, source/calendar coverage and live browser/push delivery remain incomplete.


## News collection, app read path and owner alerts — 28 Nov 2026

- Added trusted publisher-policy bootstrap from `CONTROLADOR_NEWS_SOURCE_POLICIES`; source identity and tier are host-controlled, with overlapping/ambiguous host scopes rejected. RSS feed URLs and publisher trust remain separate configuration controls.
- Wired the trusted evidence store into StandaloneRuntime. The background poller owns collection; the Analysis/news read path consumes its cached batch and persisted evidence instead of polling the feeds again on every request. Managed runtime does not fall back to request-time HTTP polling when its worker is absent.
- Preserved direct non-managed EcosystemService compatibility for tests/adapters, but it resolves each article URL through the explicit trusted source policy before ingestion; unknown publishers become partial evidence errors rather than implicit trusted sources.
- Worker reports cache freshness, successful/partial/unavailable state and configured-feed coverage. Partial feed reachability is not called fully live.
- New high-review headlines can create deterministic owner-scoped alerts only for `OFFICIAL_PRIMARY` and `TRUSTED_MEDIA` sources. Commentary, duplicates and lower-review headlines do not alert. Alerts are written to the tenant inbox/outbox and the existing local single-user notification center consumed by the app/API. Notification failures are isolated from evidence-ingestion status.
- Active matching memory is bounded to 72 hours and 5,000 records. Older published headlines remain in the append-only SQLite audit store but do not participate in recent corroboration. Disk retention/compaction is still open.
- Added `docs/NEWS_SOURCE_CONFIGURATION.md` and `docs/NEWS_SOURCE_CATALOG.md`. The catalogue lists official starter feeds and official feed directories for the Federal Reserve, ECB, BLS, SEC, Bank of Japan, Bank of Canada and BCB. The feed endpoints have not been live-tested from the deployed runtime; source acceptance still requires deployed health/freshness checks.
- Added regression coverage for trusted source configuration, cached reads, no request-time polling in managed runtime, owner-scoped evidence, high-impact alert gating, duplicate suppression, commentary suppression, notification error isolation, partial feed coverage and bounded recent evidence loading.
- Code head `aabf60b9e6e7261a9c429886d7be4683fb1968cc`: CI run [46169604443](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46169604443) has passed P1.9, full test suite, dependency security audit, Python compilation, production container build and production health smoke; standalone analyst container build was still running at ledger update time, so the overall workflow is not yet marked passed. Windows PowerShell validation passed.
- Catalogue documentation commit: `3bdc68885eeaa32f62dc75073ce717413ba1a7f3`. This ledger update is documentation-only.
- Still open: full-article retrieval and claim/contradiction extraction; broad journalism feed validation and economic-calendar adapters; source freshness tests in deployed hosting; shared production database/KMS and multi-replica worker; browser/mobile closed-app push acceptance; real MT5/cTrader market feed validation; and Lovable screen-by-screen API acceptance. No Lovable UI was changed, no EA/FOMO added, no order execution or money movement enabled, and no PR merge/deployment performed.


### Final CI result for the news integration code head

- CI run [46169604443](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46169604443) completed successfully on code head `aabf60b9e6e7261a9c429886d7be4683fb1968cc`.
- All four jobs passed: main CI (P1.9 robustness tests, full suite, dependency audit, Python compilation, production container build/health smoke and standalone analyst container build/health smoke), Windows PowerShell validation, protected-branch compatibility, and required commit-status publication.
- The curated source catalogue and subsequent completion-ledger updates are documentation-only commits on top of the tested code head; no application code changed after the successful run.
- This CI pass does not constitute live RSS feed acceptance, hosted worker continuity, multi-replica production storage, full-article verification, real broker market-data validation, push delivery with the app closed, or Lovable end-to-end acceptance.


## Registered strategy replay — 28 November 2026

- Added a research-only replay adapter for the existing in-repository `StrategyPipeline`, with explicit version `technical-pipeline-v1` and a 30-closed-candle warm-up. Each historical decision is generated from the current candle and prior history only; unknown strategy versions are rejected.
- Exposed `evaluate_registered_strategy_trial` through the existing Estudo handler, using the server-injected tenant/subject context and the existing append-only strategy trial ledger. The request cannot override tenant identity.
- Added integration tests for registered strategy dispatch, generated-decision provenance, tenant isolation, and rejection of unregistered strategy versions.
- This closes the earlier gap where the only historical evaluator accepted caller-supplied decisions, but it does **not** complete robust strategy recommendation: candles are still caller-supplied rather than fetched from immutable provider snapshots; the backtest remains gross of spread/commission/slippage; strategy variants/trial returns are not fully captured; and `evaluate_strategy_robustness`/CSCV/DSR are not yet wired into the Estudo promotion workflow.
- Research replay is diagnostic only: `promotion_allowed=false`, `execution_authorized=false`, and no orders are submitted. No probability-of-profit claim is made.
- Commits: `7dcebb39` (registered replay adapter), `a499ee58` (Estudo API wiring), `37c9f112` (integration tests).
- GitHub has not yet reported a workflow run for exact latest test commit `37c9f112be5d2c24691e4faa2f1d4e08acb3d34b`; this increment is **not yet CI-validated**.


## CI failure diagnosis and compatibility correction — 28 November 2026

- CI run [46180914941](https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/46180914941) failed the full suite with 1 failure, 2,642 passed and 44 subtests passed. The failure was not in the newly added registered-strategy replay: an existing news-classification test expected the legacy limitation key `full_article_not_verified`, while the current classifier emitted the newer equivalent `not_verified_against_full_article`.
- Restored the legacy audit key as an additional backward-compatible limitation while retaining the more explicit current key. No classification behavior or trust level was weakened.
- Correction commit: `1b472d1a03b87dc1226ca4e2d6a6de4c5f13f358`.
- GitHub had not yet exposed a workflow run for the correction commit at the time of this ledger update. The corrected code is therefore **not yet CI-validated**. Do not treat the prior failed run as a pass or the correction as validated until a fresh full run succeeds.


## Auditoria retroativa da fundação — 28 de novembro de 2026

- Criado docs/FOUNDATION_RETROACTIVE_AUDIT.md para recuperar pendências anteriores e impedir perda de trabalho entre o Project Master Specification, addenda, planos, testes, status de conclusão e PRs.
- Descoberta: o master spec dizia que P53 era o último marco confirmado, mas o repositório contém addenda/planos P54–P127 e o status de conclusão declara artefatos P128–P149. O master spec foi corrigido para apontar os artefatos recuperados, sem inventar conteúdo de marcos ausentes.
- P54–P110: addenda e famílias de módulos/testes localizadas para validação de hipóteses, conhecimento confiável, memória, auditoria, laboratório, adaptação, governança, uso controlado, feedback e validação.
- P111–P119: addendum de pré-REAL/liberação controlada localizado. Contratos de autorização não constituem autorização operacional.
- P120–P127: planos individuais recuperados para resultado, reconciliação externa, dados de mercado, ordem, sessão, sandbox/DEMO, segurança pré-REAL e integração IC Markets MT5 DEMO.
- P128–P149: PROJECT_COMPLETION_STATUS.md declara essa faixa; arquivos P128, P138 e P139 foram localizados. A auditoria individual de todos os artefatos e da integração runtime/API permanece aberta.
- P1–P22: a recuperação individual continua pendente; o master spec mantém os artefatos históricos como fonte de verdade e proíbe reconstrução por suposição.
- Contradição de autorização REAL corrigida em docs/STANDALONE_COMPLETION_ROADMAP.md: a abertura agora mantém SIMULAÇÃO como modo ativo e REAL/ordens/movimentação financeira desabilitados nesta fundação. P111–P119 e P120–P126 são contratos históricos de segurança, não ativação atual.
- Evidência de round-trip MT5 DEMO em PROJECT_COMPLETION_STATUS.md (01/10/2026) permanece evidência histórica daquele ambiente; não comprova conexão do novo aplicativo standalone hospedado.
- O relatório inclui pendências transversais antigas: snapshots imutáveis de provider no Estudo, custos reais de backtest, trials/retornos completos para DSR/CSCV, calendário oficial, artigo integral e conflitos de notícias, vídeo-análise ponta a ponta, contexto cross-market, síntese adversarial, persistência/identidade/KMS, workers hospedados, push com app fechado, Reserva Fiscal, Assistente read-only e aceitação tela a tela do Lovable.
- GitHub Actions run 46181167812 passou nos quatro jobs para o head anterior 11c5ccddb4fa39a88dedff0464e3b55cc8865e20: CI completo, validação Windows PowerShell, compatibilidade da branch protegida e publicação dos status obrigatórios.
- As alterações desta auditoria são documentação. O PR #534 continua draft, aberto e não mesclado; sem deploy, sem alteração do Lovable, sem REAL, sem envio de ordens e sem movimentação de dinheiro.
- Estado: auditoria documental inicial registrada; P1–P22 e P128–P149 precisam de recuperação/verificação individual, e P54–P127 precisam de aceitação integrada, não apenas presença de código/testes.
