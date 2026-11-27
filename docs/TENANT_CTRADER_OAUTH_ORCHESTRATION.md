# Tenant-scoped cTrader OAuth orchestration

TenantCTraderOAuthService joins the tenant-bound one-time OAuth state vault to the encrypted token vault.

- `begin()` accepts only an owned, pending `ctrader_open_api` connection and returns a Spotware consent URL containing one-time state.
- `complete_callback()` consumes state atomically, resolves the owner and connection from server-side state, exchanges the code through a host-injected OAuth client, validates token expiry, and stores tokens only through `TenantOAuthTokenVault`.
- OAuth callback completion does **not** mark an account CONNECTED. The account remains PENDING until a later account-list selection, DEMO-mode verification, account-auth handshake, and read-only market-data adapter binding.
- The OAuth exchange client and production KMS cipher are host dependencies. No production credentials or KMS implementation are bundled here.
- Never expose authorization codes, access tokens, refresh tokens, client secrets, or raw OAuth state in logs.

The test cipher is reversible and test-only. It is not suitable for production.

## HTTP integration

- Authenticated owner starts consent with `POST /api/market-data/connections/{connection_id}/ctrader-oauth`. The response returns the one-time authorization URL; the caller must not persist or log the raw OAuth state.
- Spotware redirects to `GET /api/oauth/ctrader/callback?code=...&state=...`. The route accepts HTTPS only (direct TLS or an explicitly trusted TLS-terminating proxy), consumes the one-time state, and resolves the tenant and connection from the server-side vault. No tenant, subject, or connection identifiers are accepted from callback query parameters.
- The standalone runtime exposes this flow only when all four host dependencies are injected: authenticated-encryption KMS cipher, authorization-code exchange client, cTrader client ID, and HTTPS redirect URI. Partial configuration fails startup. Without these dependencies, routes fail closed with service unavailable.
- The exchange client is responsible for calling Spotware's token endpoint over TLS, authenticating with the server-side client secret, enforcing timeouts, and redacting codes/tokens from logs. The runtime does not ship a fake or default exchange implementation.
- The callback returns a pending status. A later provider transport must enumerate accounts, reject live accounts, authenticate the selected DEMO account, and bind verified read-only market data before the registry may mark the connection CONNECTED.
