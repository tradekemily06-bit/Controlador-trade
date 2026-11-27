# Tenant OAuth state vault

TenantOAuthStateVault is the server-side CSRF and replay-protection primitive for broker OAuth callbacks (initially cTrader).

- Issues a high-entropy, one-time state only for a PENDING connection owned by the authenticated tenant and subject.
- Persists only the SHA-256 digest, never the raw state.
- Binds the state to tenant, subject, connection and provider on the server.
- Enforces a short configurable lifetime (60–1800 seconds; default 10 minutes).
- Consumes atomically under SQLite BEGIN IMMEDIATE; a second callback/replay is rejected.
- Expired and consumed rows are cleaned during issuance.
- Provider allowlist is server-controlled; callback input cannot choose or override the provider.

This is a security building block, not a complete OAuth integration. It does not exchange authorization codes, store/refresh access tokens, expose a callback route, or establish a cTrader session. Do not mark a provider CONNECTED based only on a consumed state. A subsequent code exchange, token vault write, account-list validation, DEMO verification and account-auth handshake are still required.

Official references:
- https://help.ctrader.com/open-api/account-authentication/
- https://help.ctrader.com/open-api/python-SDK/python-sdk-index/
