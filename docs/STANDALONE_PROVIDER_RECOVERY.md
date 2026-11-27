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

Provider onboarding also rejects any handshake capability outside the
read-only market-data scope. Capabilities must end in `:read` or `:stream`,
except the explicit `account-mode:demo` marker. A provider advertising
`orders:write`, trading scopes, or another write capability is rejected and
its adapter is closed before a connection is persisted.

All provider adapters remain read-only and every recovery result carries
`execution_authorized: false`. This mechanism does not configure a production
secret manager, KMS, distributed database, or 24/7 hosting by itself.
