# Tenant-scoped cTrader OAuth orchestration

TenantCTraderOAuthService joins the tenant-bound one-time OAuth state vault to the encrypted token vault.

- `begin()` accepts only an owned, pending `ctrader_open_api` connection and returns a Spotware consent URL containing one-time state.
- `complete_callback()` consumes state atomically, resolves the owner and connection from server-side state, exchanges the code through a host-injected OAuth client, validates token expiry, and stores tokens only through `TenantOAuthTokenVault`.
- OAuth callback completion does **not** mark an account CONNECTED. The account remains PENDING until a later account-list selection, DEMO-mode verification, account-auth handshake, and read-only market-data adapter binding.
- The OAuth exchange client and production KMS cipher are host dependencies. No production credentials or KMS implementation are bundled here.
- Never expose authorization codes, access tokens, refresh tokens, client secrets, or raw OAuth state in logs.

The test cipher is reversible and test-only. It is not suitable for production.
