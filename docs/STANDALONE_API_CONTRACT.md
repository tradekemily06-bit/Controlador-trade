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

### `GET /api/readiness`
Consolidated diagnostic for the frontend's connection/status indicators. Returns:
- architecture and area count;
- market-data registry status;
- candle monitor status;
- news provider status;
- assistant readiness;
- in-app notification/outbox summary;
- external notification worker status;
- identity policy status, including explicit unconfigured trusted identity provider and missing multi-tenant isolation;
- decision-memory persistence mode/state, including explicit in-memory-only or persistence-error status; only `PERSISTENT_READY` is reported as durability confirmed for that local SQLite store;
- tenant-scoped local preference-store status, explicitly not production-ready;
- deployment marker `PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED`.

A configured/registered provider is not proof of a live connection. The deployment marker is deliberately not a production deployment claim.

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
Lists provider registration/configuration status. Status values must not be presented as proof of a live feed.

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
Body: `{"message":"...","conversation_id":null}`. Currently enabled only for the configured local single-user runtime. A tenant-separated local fiscal repository factory and per-tenant on-demand backup primitive now exist, but they are not yet wired into remote request handling or assistant context collection. Remote chat therefore remains deliberately rejected with `FISCAL_TENANT_ISOLATION_REQUIRED`. Conversation list/history/delete are tenant-scoped for remote identities; remote chat will be enabled only after the verified identity boundary, fiscal repositories, context collection and backup/restore lifecycle are integrated and tested end-to-end.

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
- The legacy single-user runtime remains the active fiscal path until integration and migration are validated. Remote assistant chat and cross-area routes remain blocked where shared state exists.



## Decision-memory persistence status
- `GET /api/readiness` includes `decision_memory`, reporting `mode`, `state`, `last_error_class` and `durability_confirmed`.
- `IN_MEMORY_NOT_CONFIGURED` means decision history is not durable across process restarts.
- `PERSISTENCE_ERROR` means SQLite initialization or I/O failed; the application may continue fail-soft, but the memory must not be described as persisted.
- `PERSISTENT_READY` confirms that the local SQLite store initialized successfully. It does not prove backup/restore, multi-tenant isolation, or production database operations.
