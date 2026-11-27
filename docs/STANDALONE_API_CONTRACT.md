# Standalone application API contract

This contract is for connecting the existing approved frontend without changing its layout. All responses are read-only with respect to broker execution and money movement. No order endpoint exists.

## Access and transport

- Base URL is supplied by deployment; use HTTPS outside localhost.
- JSON request/response bodies use UTF-8.
- Local loopback access is intended only for the configured single-user runtime. Remote access is denied unless remote access is explicitly enabled, a server-side access token is valid, and trusted authentication middleware injects a verified subject (`REMOTE_USER`), `controlador.identity_verified=True`, and a non-empty `controlador.tenant_id` into the WSGI environment.
- Set `CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE=1` only when a trusted server-side middleware is actually installed and strips any client-supplied identity claims. The application does not trust identity values from ordinary HTTP headers.
- The shared bearer token is an additional access gate, not a user identity. A middleware flag alone does not prove a provider is configured or runtime-verified. Tenant-scoped local preferences are available, but other legacy stores and the full application lifecycle are not yet multi-tenant; the product must not be presented as production multi-user SaaS.
- Cross-origin browser access is disabled unless `CONTROLADOR_ALLOWED_ORIGINS` contains the exact comma-separated frontend origins (scheme + host + optional port). Wildcard origins are not supported. CORS preflight is rate-limited and permits only GET, POST, DELETE and OPTIONS with Authorization/Content-Type headers.
- The MT5 relay ingest route uses its own dedicated bearer token and HTTPS/TLS validation.
- Never expose server tokens, provider credentials, or relay secrets in browser code.

## Core application

### `GET /api/health`
Liveness response: service name, architecture identifier, visible area count and `execution_authorized: false`.

### `GET /api/backup/status` and `GET /api/bridge/mt5/status`
Local single-user operators receive detailed local backup/relay status. Verified remote tenants receive only a minimal `INFRASTRUCTURE_ONLY` response: shared backup result paths/history, relay source identifiers, candle totals and global heartbeat metadata are not exposed. These are host-wide operational resources, not tenant-owned records. Neither endpoint authorizes execution.

### `GET /api/readiness`
Read-only diagnostic for frontend connection/status indicators. The response is intentionally scope-dependent:

- Local single-user runtime: returns the detailed diagnostic, including architecture/area count, provider registry, candle monitor, news, assistant, notification/outbox worker, identity policy, local persistence states, tenant-store readiness and deployment marker.
- Verified remote tenant: returns only an `INFRASTRUCTURE_ONLY` contract with architecture/area count, identity-policy status and pointers to the dedicated tenant-scoped status endpoints. It does not expose global notification counts, assistant counters, shared storage details, or cross-user monitor state.

Remote clients must use `GET /api/notifications/status` for their own notification count and `GET /api/market-monitor/status` for their own subscriptions. Other personal data must be read through its dedicated tenant-scoped endpoint. This split prevents a shared readiness response from becoming a side channel for another user's operational data.

A configured/registered provider is not proof of a live connection. The deployment marker is deliberately not a production deployment claim. All variants return `execution_authorized: false`.

### `GET /api/areas`
Returns the seven visible application areas.

### `GET /api/intelligence/architecture`
Returns area descriptions, shared-intelligence architecture and handler status.

### `POST /api/intelligence/route`
Body:
```json
{
  "area": "analysis",
  "task": "analyze selected market",
  "context": {
    "operation": "overview",
    "symbol": "EURUSD",
    "timeframe": "M5"
  }
}
```
The area and task are required strings; context must be an object. The selected area handler determines supported context fields. Market analysis remains manual-review only; no order is submitted.

## Market data and timeframe monitoring

### `GET /api/market-data/providers`
Lists provider registration/configuration status. A provider exposing a side-effect-free `status()` may report a verified fresh connection heartbeat (`CONNECTED`/`DISCONNECTED`) and a bounded set of non-secret health fields. Providers without that capability remain `REGISTERED_NOT_TESTED`; a heartbeat does not prove every symbol/timeframe is available or guarantee uninterrupted delivery. Status polling does not initialize or probe a broker terminal. Status values must not be presented as proof of a live feed beyond the precise heartbeat evidence reported.

### `GET /api/market-data/timeframes`
Returns the intervals accepted by the backend normalizer in compact and platform notation, with limits and explicit exclusions. The current parser covers 1–59 minutes, 1–24 hours, 1–31 days and 1–4 weeks. Seconds and calendar months (MN1) are not supported. The response also reports adapter-declared `provider_compatibility.supported` and `unsupported` intervals when the adapter exposes a side-effect-free capability check. `DECLARED_NOT_LIVE_TESTED` means the adapter can map/derive the interval but real data availability has not been tested; `NOT_DECLARED` means the adapter does not publish a capability list. A supported interval is never a claim of a live feed. The frontend should use this endpoint for the selector while showing provider availability separately.
### `GET /api/market-monitor/status`
Returns worker state and only the enabled subscriptions belonging to the tenant and subject resolved by trusted server identity. The worker-running flag is operational metadata. The worker rechecks that a subscription remains enabled before analysis and again before publishing a result or notification.

### `GET /api/market-monitor/subscriptions`
Returns persisted symbol/timeframe subscriptions belonging only to the resolved tenant and subject.

### `POST /api/market-monitor/subscriptions`
Body: `{"symbol":"EURUSD","timeframe":"M5"}`. Creates a subscription under the resolved tenant and subject. Each owner has an independent limit of 100 active subscriptions.

### `DELETE /api/market-monitor/subscriptions`
Body: `{"symbol":"EURUSD","timeframe":"M5"}`. Disables only the matching subscription owned by the resolved tenant and subject.

### `GET /api/market-monitor/results?limit=50`
Returns recent closed-candle results only for the resolved tenant and subject. Limit is 1–200. A stale, incomplete, invalid or unsupported feed must remain non-actionable/AGUARDAR.

## User preferences

### `GET /api/user/preferences`
Returns preferences stored under the authenticated tenant and subject scope. On local loopback, the scope uses the configured single-user runtime identity.

### `PUT /api/user/preferences`
Body: `{"preferences":{"language":"pt-BR"}}`. The preferences value must be a JSON object. Data is stored in the dedicated tenant-state SQLite database and isolated by tenant ID. No legacy global preferences are copied or reassigned automatically.

This is local tenant-scoped persistence, not proof of a production identity provider, managed database, backup/restore, or complete multi-tenant isolation. The route is informational/configuration-only and never authorizes broker execution.

## Tenant-scoped decision memory

The runtime provisions a tenant-and-subject-scoped decision-memory adapter on the local tenant SQLite store. Each market analysis is now saved under the configured local runtime owner using a stable ID derived from symbol, timeframe, and closed-candle timestamp. Repeated analysis of the same candle is idempotent and does not overwrite manually annotated outcomes. The adapter supports explicitly addressed save/load and manual outcome annotation, validates decision records, and never imports the legacy global decision history. The remote memory API resolves ownership from trusted server identity. The dedicated statistics and report endpoints now calculate only from this tenant-scoped memory. The generic remote application route remains blocked until the broader cross-area handler lifecycle (including learning, assistant, fiscal and legacy service state) is tenant-isolated. The adapter remains local SQLite and is not production-durable.

### Decision memory API

#### `GET /api/memory/decisions?limit=100`
Returns decision records only for the trusted tenant and subject resolved by the server. The limit is 1–2000. Local loopback uses the configured single-user identity; remote access requires verified server-injected identity.

### Local read-only fiscal summary

#### `GET /api/fiscal/summary?limit=100&offset=0`
Returns the configured local single-user owner's fiscal reserve summary and paginated ledger history. `limit` is 1–500 and `offset` is 0–100000. The response is explicitly marked `scope: LOCAL_SINGLE_USER`, `tax_assessment: false`, `money_movement: false` and `execution_authorized: false`. The summary remains a planning estimate, not a tax assessment.

Remote identities receive `FISCAL_REMOTE_STORAGE_NOT_READY`; this endpoint deliberately does not read the legacy single-owner fiscal database for remote users. The per-tenant fiscal repository factory exists as a local isolation primitive, but production-grade remote fiscal reads are not enabled until its storage lifecycle and trusted identity integration are validated.

### Tenant-scoped market analysis

#### `POST /api/analysis/run`
Body: `{"symbol":"EURUSD","timeframe":"M5","limit":120}`. Runs the existing read-only market analysis pipeline for the resolved tenant and subject, then saves the resulting decision to that owner's decision memory. The timeframe is normalized by the backend and must be supported by the configured provider. `limit` is 3–1000 and defaults to 120. The server forces `confirmed=false` and `filters_ok=true`; client-supplied confirmation/filter flags are ignored. The response includes `execution_authorized: false` and `order_submitted: false`. Local requests use the configured single-user identity; remote requests require trusted server-injected tenant and subject identity. A missing provider returns `ANALYSIS_NOT_CONFIGURED`; no cached or fabricated market data is substituted.

The generic cross-area `POST /api/intelligence/route` remains blocked for remote users because its handlers include shared learning, assistant, fiscal and legacy service state. The dedicated market-analysis endpoint does not invoke those shared handlers.

`GET /api/assistant/status` also reports the conversation identity scope and whether remote chat is blocked pending fiscal isolation. Provider credentials being configured does not mean the provider connection has been tested.

### Assistant conversation APIs

#### `GET /api/assistant/conversations`
Lists conversations belonging only to the resolved tenant and subject. The owner key is derived from the trusted `TenantContext`; client-supplied owner IDs are never accepted.

#### `GET /api/assistant/conversations/history?conversation_id=...`
Returns history only when the conversation belongs to the caller. A conversation ID from another tenant/subject returns not found.

#### `DELETE /api/assistant/conversations`
Body: `{"conversation_id":"..."}`. Deletes only a conversation owned by the resolved tenant and subject.

#### `POST /api/assistant/ask`
Body: `{"message":"...","conversation_id":null}`. Local requests use the configured single-user fiscal context. Verified remote identities are routed through `EcosystemAssistant.ask_tenant`, which derives both conversation ownership and fiscal repositories from the trusted immutable `TenantContext`; callers cannot submit an owner ID or shared fiscal context. If the tenant fiscal factory or tenant-aware method is missing, the route fails closed with `FISCAL_TENANT_ISOLATION_REQUIRED`. The remote path is covered by request-boundary tests, but production identity-provider deployment, durable managed storage, backup/restore operations and end-to-end hosted validation remain outstanding.

All assistant routes remain read-only: no orders, REAL activation, or money movement.

### Tenant-scoped analysis statistics and reports

#### `GET /api/analysis/statistics`
Returns totals, manually recorded outcomes, historical outcome ratio, UTC periods and breakdowns by symbol, timeframe, signal and score band. The calculation loads only the decision records owned by the verified tenant and subject. The win rate is a historical ratio of manually annotated closed outcomes, not a prediction or calibrated probability.

#### `GET /api/analysis/report?limit=1000`
Builds a read-only JSON report from the same tenant-scoped decision memory. `limit` is 1–1000 for the displayed record list; report statistics are calculated over all records loaded from that owner's memory (currently bounded to 2,000 records). No legacy global `DecisionStore` data is read or reassigned. Both endpoints are available locally to the configured single user and remotely only with trusted server-injected identity.

The generic `POST /api/intelligence/route` remains blocked for remote users: although these dedicated analytics endpoints are isolated, the wider area-handler lifecycle still contains shared learning, assistant, fiscal and legacy service state that has not been comprehensively converted to tenant-scoped persistence.

#### `POST /api/memory/decisions/outcome`
Body: `{"decision_id":"...","outcome":"WIN"}`. Accepts only manual-study outcomes (`WIN`, `LOSS`, `DRAW`, `OPEN`, `VOID`) for a record already owned by the resolved tenant and subject. It cannot grant execution authority.

The endpoint uses the new tenant-scoped decision store. Historical records in the legacy global decision database are not automatically copied or attributed to a user. The adapter is local SQLite and not production-durable.

## Notifications

### `GET /api/notifications?limit=50&include_info=false`
Returns the in-app notification inbox. Limit is 1–200. This endpoint does not mark notifications as read.

- Local loopback uses the configured single-user runtime inbox.
- Remote requests require verified server-injected tenant and subject identity and read only the matching tenant-scoped notification collection. They never read the legacy global operational inbox.
- The runtime binds its configured `CONTROLADOR_SINGLE_USER_IDENTITY` to a local tenant context before starting market monitoring. Every market-monitor subscription and result is keyed by tenant ID + subject ID + symbol + timeframe. Remote subscription creation, listing, cancellation, status and result reads use only the tenant context injected by trusted server middleware. The worker processes each saved subscription with that owner's context; decision records and material signal notifications are written to the same owner's tenant-scoped stores. The monitor's previous single-user tables are migrated only to the explicitly configured local owner, never attributed to remote users. Tenant inbox append is an atomic SQLite transaction with deduplication and bounded retention; there is no global notification broadcast.
- This API boundary prevents cross-user reads; it does not mean the entire application or every legacy store is multi-tenant.

`/api/market-monitor/*` now enforces per-tenant/per-subject ownership and has isolation tests. Remote `POST /api/intelligence/route` remains blocked because the broader application statistics and report-generation pipeline is still shared and has not been made tenant-scoped. This is a partial multi-tenant foundation, not a completed multi-tenant SaaS implementation.

### `GET /api/notifications/status`
Returns persistence/outbox counts and external worker status. `OUTBOX_ONLY_NO_PROVIDER` means notifications are stored in the app but no external delivery sink is configured. Do not display this as phone/browser push enabled.

## Assistant

### `GET /api/assistant/status`
Returns assistant readiness. A ready internal assistant does not imply that a model-provider credential is configured or that a live provider request has succeeded.

## MT5 relay (local agent only)

### `POST /api/bridge/mt5/candles`
Accepts validated closed-candle batches from the local Windows agent. Requires the dedicated relay bearer token and HTTPS (or an explicitly trusted TLS-terminating proxy). The local agent is outbound-only; no EA or inbound PC port is required.

### `GET /api/bridge/mt5/status`
Returns relay inbox status. A configured relay is not proof that the user's PC is currently connected; verify received timestamps and a real test batch.

## Product and safety invariants

- Seven visible areas remain fixed: Cabine de Comando, Análise, Estudo, Memória, Reserva Fiscal, Assistente do Ecossistema and Central.
- The approved frontend design is unchanged by this backend contract.
- Signal direction is informational; manual review is required.
- No endpoint authorizes broker orders, trades, or money movement.
- Browser/device push requires a push provider, subscription registration, service worker and permission flow; it is not enabled by the in-app inbox or outbox alone.


## Foundation storage integrity
- `GET /api/readiness` now includes `storage_foundation`.
- The endpoint runs read-only SQLite `PRAGMA quick_check` against the five required local stores (fiscal, ecosystem state, notification outbox, decision memory, assistant conversations) and reports optional market-monitor storage separately.
- A missing or unreadable required database degrades the reported foundation status. The check does not create, migrate, repair, or modify databases.
- This is local SQLite integrity evidence only. It does not establish production-grade multi-tenant isolation, backup/restore, managed database availability, or deployment readiness; those remain explicitly unconfigured/not proven.

## Tenant fiscal storage and backup primitives
- `finance/tenant_fiscal_store.py` creates one local SQLite fiscal database per trusted tenant + subject context. It uses an opaque digest for the on-disk path and initializes the domestic queue, foreign queue and reserve ledger in that isolated database.
- `core/tenant_fiscal_backup.py` creates an explicit, on-demand backup for exactly one supplied tenant + subject. It uses SQLite's backup API, validates the complete fiscal table/owner scope and foreign keys, and publishes without overwriting an existing backup.
- The same service can validate a backup by restoring it into a temporary isolated SQLite file, checking integrity, required fiscal tables, owner scope and foreign keys. This test never replaces or modifies the live database.
- These are isolated storage/backup primitives only. They are not yet connected to remote fiscal routes or assistant context collection; they do not enumerate tenants, schedule backups, or replicate off-host. This is not a production disaster-recovery workflow.
- The standalone runtime now registers `TenantFiscalStoreFactory` and exposes `tenant_fiscal_storage` in `GET /api/readiness`. Its status explicitly reports `remote_request_wiring: NOT_ENABLED`, `production_durable: false` and `backup_restore: NOT_VERIFIED` until the complete remote identity, persistence and recovery path is validated.
- The legacy single-user runtime remains the active fiscal path until integration and migration are validated. Remote assistant chat and cross-area routes remain blocked where shared state exists.



## Decision-memory persistence status
- `GET /api/readiness` includes `decision_memory`, reporting `mode`, `state`, `last_error_class` and `durability_confirmed`.
- `IN_MEMORY_NOT_CONFIGURED` means decision history is not durable across process restarts.
- `PERSISTENCE_ERROR` means SQLite initialization or I/O failed; the application may continue fail-soft, but the memory must not be described as persisted.
- `PERSISTENT_READY` confirms that the local SQLite store initialized successfully. It does not prove backup/restore, multi-tenant isolation, or production database operations.


## Contexto fiscal isolado do Assistente (preparação)

O módulo `assistant.tenant_read_only_context.collect_tenant_fiscal_context(factory, tenant_context)` recebe a fábrica fiscal e um `TenantContext` imutável, resolve internamente os repositórios do proprietário e monta um contexto fiscal sanitizado. Ele não aceita um pacote de repositórios fornecido pelo chamador e exclui status, risco, estatísticas, observabilidade e memória do `EcosystemService` compartilhado. O contexto continua sendo apenas uma primitiva de preparação: não está conectado à rota remota `/api/assistant/ask`, e o chat remoto permanece bloqueado até a integração da identidade confiável, persistência, backup/restauração e validação ponta a ponta. A separação é coberta por `tests/test_tenant_assistant_context.py`. O serviço `EcosystemAssistant.ask_tenant(tenant_context, fiscal_store_factory, message, cid=None)` agora oferece uma via de conversa isolada: deriva o proprietário da conversa do `TenantContext`, carrega somente esse contexto fiscal e devolve escopo `TENANT_AND_SUBJECT`, sempre somente leitura. Esta via é uma primitiva interna testada; não está conectada à rota HTTP remota `/api/assistant/ask`. O chat remoto permanece bloqueado até a identidade confiável, persistência, backup/restauração e integração de runtime serem validados ponta a ponta.

Este módulo ainda não está ligado à rota remota `/api/assistant/ask` nem ao runtime de produção. O atendimento remoto permanece bloqueado até que identidade confiável, resolução dos repositórios por requisição, contexto completo por usuário e persistência sejam integrados e validados. Não representa liberação de chat remoto ou isolamento de produção.


## Mobile and multi-device client contract

The API is device-neutral: a verified user may call it from a desktop browser, mobile browser, or installed PWA. Device type, viewport size, and user-agent must never determine tenant ownership or grant capabilities. The same trusted identity maps the same tenant-and-subject data on every device.

- The frontend must use the deployed HTTPS API base URL, not `localhost` or a computer's private LAN address, when accessed from a phone.
- Each device authenticates independently through the same trusted identity provider. Never persist a shared server bearer token or provider secret in browser storage or mobile bundles.
- Tenant-scoped preferences, conversations, fiscal context, notifications, market subscriptions, and decision history must resolve from server-injected identity, not a device-local user ID.
- A PWA installation requires a valid web app manifest, platform icons, HTTPS, and a service worker served from the correct application origin. The current API repository does not itself serve the Lovable frontend or install its service worker; these assets must be delivered by the frontend deployment without redesigning the approved UI.
- Offline caching is limited to the static application shell. Do not cache authenticated API responses, market data, fiscal records, assistant conversations, notification contents, tokens, or account identifiers in the service worker cache.
- A phone closing the browser must not stop server-side market monitoring or notification dispatch. That requires a continuously running hosted worker, not a worker tied to the user's PC or browser process.
- Push delivery requires HTTPS, a user-granted browser notification permission, per-device push subscription registration, server-side subscription storage scoped to the trusted tenant and subject, VAPID keys kept only on the server, a real Web Push sender, expiry/revocation handling, and end-to-end tests on supported mobile browsers. Until all of these are deployed, the product must report in-app/outbox delivery only and must not claim phone push is active.
- Push payloads should be privacy-minimal (event ID and generic alert), with authenticated details fetched from the API after the user opens the app. Never include fiscal balances, credentials, or full private assistant content in a push payload.

This contract preserves one account and one backend across desktop and mobile; it does not create separate device accounts or a second mobile-only product.

## PWA assets prepared in this repository

The `web/` directory now includes:
- `manifest.webmanifest` with standalone display mode and a scalable application icon.
- `pwa/icon.svg` as the public install icon.
- `service-worker.js` with a strict public-asset cache allowlist; it never caches navigation HTML, API responses, market data, fiscal data, assistant conversations, or private notifications.
- `pwa-registration.js` as a no-layout-change registration module for the deployed frontend shell.
- `pwa_foundation_test.py` to protect the manifest, registration and cache-safety contract.

These are prepared integration assets, not proof of a deployed installable app. The registration module is intentionally not injected into the Lovable frontend; that connection must happen only when the approved frontend is explicitly integrated. The current API repository does not yet serve these assets as the public production origin. Push event handling is prepared in the service worker, but server-side push subscriptions, encrypted subscription storage, VAPID signing/sending, and device delivery validation remain unimplemented.
