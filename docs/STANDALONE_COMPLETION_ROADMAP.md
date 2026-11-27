# Standalone Controlador-trade — completion roadmap

This roadmap defines the evidence required to call the independent application complete. It does not change the approved Lovable interface, enable broker orders, or replace the existing implementation with a new app.

## Delivery boundaries

- One standalone application, backed by the existing seven visible areas: Cabine de Comando, Análise, Estudo, Memória, Reserva Fiscal, Assistente do Ecossistema and Central.
- Preserve the approved Lovable UI. Backend work must connect to its existing screens and controls; visual redesign is out of scope.
- No EA and no broker order submission. Market analysis and notifications are informational and require human review.
- DEMO-first. REAL remains unavailable until separately reviewed, explicitly authorized, and validated; this roadmap does not authorize REAL execution.

## Evidence status — 27 November 2026

This is the current implementation boundary, not a release declaration:

| Front | Implemented in repository | Still required before claiming complete |
|---|---|---|
| Analysis and signal validity | Per-timeframe closed-candle cycles; expiry; tenant/account/source isolation; signal evidence and next-candle directional outcomes; strict separation from profit probability | Validate continuous real provider feeds, complete walk-forward dataset and separately approved calibrated probability model; verify costs/executable outcomes before any profit estimate |
| Provider connections | MT5 outbound DEMO relay; cTrader official DEMO transport, OAuth/token-vault contracts, account recovery and closed-candle stream wired to tenant timeframe monitor | Provision secrets/KMS and a real provider account; demonstrate handshake, fresh stream, candle continuity, restart/reconnect and signal cycle in the hosted environment; verify each advertised interval per provider |
| Notifications | Tenant-scoped transactional inbox/outbox, background worker contract, retries, dead-lettering, idempotency, owner-scoped status and local backup coverage | Configure a real tenant-aware delivery sink; deploy encrypted device subscriptions, VAPID/Web Push sender and hosted worker; test delivery/revocation on physical devices while app/browser is closed |
| Production foundation | Fail-closed identity/storage/security contracts, local SQLite topology guard, backup/restore primitives and container smoke tests | Deploy trusted identity, shared transactional database, distributed leases, KMS, TLS, durable audit, centralized rate limits, off-host backup and restore drill |
| Lovable integration | Existing API and notification endpoints are available; backend work preserves the frontend as the visual source of truth | Complete screen-by-screen integration and browser network acceptance in the owner-managed Lovable environment; this repository work does not claim that frontend integration has been verified |

The current automated CI run is evidence of code/test/build behavior only. It does not prove real-account connectivity, production provisioning, physical-device delivery or user acceptance. SQLite remains single-host/single-runtime, external push remains disabled by default, and REAL execution remains disabled.

## Phase A — Foundation and reuse

**Goal:** establish the stable backend used by every area.

- Shared intelligence, area routing and existing module reuse.
- Durable stores for decisions, learning, assistant conversations, fiscal queues, notifications and monitor state.
- Provider-neutral market-data contracts, provider registry and timeframe normalization.
- API contract, identity boundary, process lifecycle and fail-closed safety defaults.

**Exit evidence:** migrations and persistence tests pass; API schemas are documented; all seven areas are represented; no hidden order/money-movement route exists; a clean startup and shutdown succeeds.

## Phase B — Frontend/API integration

**Goal:** connect the existing Lovable interface without changing its appearance.

- Map each existing screen/control to the documented API route and response schema.
- Connect area navigation, selected symbol/timeframe, status indicators, analysis results, history, fiscal queues, assistant context and notification inbox.
- Handle loading, empty, stale, unavailable, unauthorized and recoverable-error states.
- Verify signal presentation: COMPRA green with upward arrow, VENDA red with downward arrow, AGUARDAR yellow; evidence score must not be described as win probability.
- Keep the profit-probability field explicitly unavailable until a calibrated, representative outcome dataset exists.

**Exit evidence:** a screen-by-screen integration matrix is complete; every visible control has a working action or is clearly unavailable; browser network traces show correct API calls; no frontend redesign or hardcoded fake live data.

## Phase C — Live data and cycle monitoring

**Goal:** prove that the selected data source delivers valid closed candles for each selected symbol/timeframe.

- Configure at least one real read-only provider and validate its actual symbol catalogue, timestamps, candle continuity, freshness and supported intervals.
- For MT5, install and configure the outbound-only local Windows bridge, provision its dedicated secret, and validate HTTPS, replay protection, freshness and DEMO-only account mode.
- Test M1, M5, M10 and every additional interval claimed in the UI against actual provider responses. Parser support or adapter-declared support alone is not live validation.
- D1/W1 are fail-closed in the standalone analysis service until a verified provider session calendar and its next valid session boundary are explicitly passed into that service; do not use fixed 24-hour/7-day validity for broker sessions.
- Verify candle-close timing, delayed/missing candle behavior, duplicate prevention, restart recovery and signal-change notification.
- Document provider-specific unsupported intervals rather than implying every interval works on every broker.

**Exit evidence:** timestamped evidence from the real provider for each advertised interval; end-to-end local-to-cloud MT5 test if MT5 is offered; stale/gapped data safely produces AGUARDAR; restart and duplicate tests pass.

## Phase D — Notifications and continuous operation

**Goal:** deliver alerts through the channels the product claims to support.

- Keep persistent in-app inbox and outbox.
- Select and configure an external push/email delivery provider; provision credentials only in server-side secrets.
- Implement browser/device permission, subscription registration, service worker, delivery receipts, retries, deduplication, expiry and unsubscribe.
- Verify delivery while the browser/app window is closed, and distinguish queued, delivered, failed and expired events.
- Run the server/worker under a production process manager with health checks, restart policy, logs, metrics, backup and restore procedures.

**Exit evidence:** test notifications are received on supported devices while the app is closed; failure/retry and unsubscribe tests pass; worker survives restart; operational monitoring and restore drill are documented.

## Phase E — Security, deployment and end-to-end acceptance

**Goal:** prove the complete app is safe, reachable and maintainable.

- Configure production HTTPS, identity, access token/session policy, secret rotation, CORS/CSRF policy where applicable, rate limits and audit logging.
- Verify tenant/owner isolation, least privilege, backup encryption/retention and incident response.
- Deploy backend and frontend integration to the intended environment; verify DNS/TLS, persistent volumes, environment variables and migrations.
- Run end-to-end scenarios across all seven areas, including unavailable provider, lost bridge, stale feed, server restart, notification failure, unauthorized access and recovery.
- Run automated tests, security scans, dependency checks and manual acceptance against the approved interface.
- Publish known limitations and a rollback plan.

**Exit evidence:** production deployment is reachable over HTTPS; all seven areas pass their acceptance scenarios; live data and notification tests are evidenced; security and restore checks pass; no unresolved critical/high findings; owner accepts the release.

## Explicit current limitations to close

- A registered market-data adapter is not proof of a live feed.
- Timeframe parser support is not proof of broker/provider availability. The current parser accepts 1–59 minutes, 1–24 hours, 1–31 days and 1–4 weeks; seconds and calendar months (MN1) are excluded. Each provider's declared compatibility must be tested against real data.
- The MT5 relay code does not mean the user's Windows PC is connected; local agent installation, secret provisioning, cloud deployment and real batch receipt are still required.
- The notification outbox/worker does not mean phone/browser push is enabled; an external sink, service worker, subscriptions, permissions and delivery tests are required.
- A process responding to health checks is not proof of production deployment or end-to-end readiness.
- Signal evidence score is not calibrated profit probability. Do not display a fabricated percentage.

## Release definition

The application is complete only when Phases A–E have their exit evidence, the existing Lovable UI is connected without visual changes, all seven areas pass end-to-end acceptance, live data and claimed notification channels are demonstrated, and the release is deployed with security, monitoring, backup and rollback in place.
