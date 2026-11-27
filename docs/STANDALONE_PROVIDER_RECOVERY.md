# Standalone provider connection recovery

Provider sessions are process-local. The tenant-scoped connection record and
its vault reference survive a restart, but an adapter object does not. A saved
`CONNECTED` status is therefore metadata from the previous process, not proof
that a live session exists in the current process.

## Startup recovery

When the standalone runtime starts, it calls
`TenantProviderConnectionService.reconnect_available()` for its configured
single-user runtime identity. Recovery is attempted only when both a
tenant-scoped secret resolver and a provider adapter factory are configured.
For each previously active account, the service resolves the stored vault
reference again and requires a fresh provider handshake before binding a new
adapter session.

A failed attempt is isolated to that account and is reported as
`RECONNECT_FAILED`. If the required resolver or factory is missing, the
account is reported as `RECOVERY_NOT_CONFIGURED`. Neither result grants
execution permission.

Accounts explicitly disconnected by the user remain disconnected. Startup
recovery does not reconnect them.

## Connection inventory

The trusted tenant-scoped inventory is available through
`GET /api/market-data/connections`. It returns only the requesting identity's
account metadata and the current process-local adapter binding/health state.
A persisted `CONNECTED` record with no in-memory adapter is reported as
`adapter_status: NOT_BOUND` and `health_status: NOT_BOUND`; the API does not
pretend a prior process's connection is live.

## Explicit reconnection

A user may request a fresh handshake for an existing account:

- `POST /api/market-data/connections/{connection_id}/reconnect`
- Requires the trusted tenant/subject identity context.
- Accepts no credential values in the request body.
- Returns the new adapter binding only after a successful handshake.
- A missing vault reference, unavailable provider integration, or failed
  handshake leaves the account disconnected.

The route validates the connection identifier and the service verifies that
the account belongs to the requesting tenant and subject.

## cTrader DEMO recovery

The dedicated cTrader OAuth account service has its own recovery path. It
reuses the saved DEMO account identifier and tenant-owned encrypted OAuth
token, refreshes an expired access token through the configured OAuth service
when possible, then performs a new cTrader account-authentication handshake
before binding a new adapter. The original connection ID is preserved.
Accounts that fail recovery remain unbound; no live account is accepted and no
order capability is introduced. The startup result is exposed separately as
`ctrader_recovery` in local readiness.

## Credential reference handling

The connection registry stores only a validated vault pointer, never resolved
credential material. The pointer is private tenant-scoped state and is omitted
from public connection metadata and readiness responses. The secret resolver
must independently enforce the tenant/subject boundary when resolving it.

## Readiness

The local `GET /api/readiness` response includes a sanitized
`provider_recovery` section. It reports account IDs, provider IDs, recovery
states, and exception classes only. Credential references and secret material
are excluded. Remote readiness remains an infrastructure-only contract and
does not expose local account recovery details.

Provider onboarding also rejects any handshake capability outside an
explicit allowlist: `candles:read`, `candles:stream`, `quotes:read`,
`quotes:stream`, `symbols:read`, `account:read`, `market-data:read`,
`market-data:stream`, and `account-mode:demo`. At least one candle capability
is mandatory. A provider advertising `orders:write`, an unknown capability,
or quotes without candle access is rejected and its adapter is closed before
a connection is persisted.

All provider adapters remain read-only and every recovery result carries
`execution_authorized: false`. This mechanism does not configure a production
secret manager, KMS, distributed database, or 24/7 hosting by itself.
