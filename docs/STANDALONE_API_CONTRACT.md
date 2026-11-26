# Standalone application API contract

This contract is for connecting the existing approved frontend without changing its layout. All responses are read-only with respect to broker execution and money movement. No order endpoint exists.

## Access and transport

- Base URL is supplied by deployment; use HTTPS outside localhost.
- JSON request/response bodies use UTF-8.
- Protected application routes use the standalone bearer-token boundary when remote access is enabled.
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
Returns worker state, enabled subscriptions and monitor status.

### `GET /api/market-monitor/subscriptions`
Returns persisted symbol/timeframe subscriptions.

### `POST /api/market-monitor/subscriptions`
Body: `{"symbol":"EURUSD","timeframe":"M5"}`. Subscribes the monitor to a symbol and supported timeframe.

### `DELETE /api/market-monitor/subscriptions`
Body: `{"symbol":"EURUSD","timeframe":"M5"}`. Disables that subscription.

### `GET /api/market-monitor/results?limit=50`
Returns recent results for closed candles. Limit is 1–200. A stale, incomplete, invalid or unsupported feed must remain non-actionable/AGUARDAR.

## Notifications

### `GET /api/notifications?limit=50&include_info=false`
Returns the persisted in-app notification inbox. Limit is 1–200. This endpoint does not mark notifications as read.

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
