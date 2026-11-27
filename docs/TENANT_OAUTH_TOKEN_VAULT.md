# Tenant OAuth token vault

TenantOAuthTokenVault stores broker OAuth token sets only as authenticated ciphertext. It binds encryption associated data to tenant, subject, connection, provider and purpose. A ciphertext copied to another account or tenant must fail authentication.

Important boundaries:
- A host-injected KMS/envelope-encryption cipher is mandatory. There is no fallback or home-grown cryptography.
- The host cipher contract is encrypt(plaintext_bytes, associated_data=bytes) -> {key_id, ciphertext_bytes}, and decrypt(ciphertext_bytes, key_id=..., associated_data=bytes) -> plaintext_bytes.
- Access and refresh tokens are never returned by provisioning methods or written to logs. resolve() is only for trusted server-side adapter code.
- Expired tokens are not resolved; revoke() erases the stored ciphertext and marks the record revoked.
- This module does not implement a production KMS, token refresh scheduler, provider revocation API or cTrader OAuth code exchange. Those must be injected/implemented before any real account can be declared connected.
- Tests use a clearly labeled reversible fixture cipher solely to verify scoping and storage behavior. It is NOT encryption and must never be used in production.

See https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html and https://help.ctrader.com/open-api/account-authentication/.
