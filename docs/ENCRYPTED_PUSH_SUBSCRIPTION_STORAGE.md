# Encrypted tenant push subscription storage

`EncryptedTenantPushSubscriptionStore` encrypts every device record with AES-256-GCM before it reaches the storage backend.

## Contract

- The host injects a tenant-scoped backend implementing get/put/delete/list_keys and explicitly declaring production_durable=True. `list_keys` must return only keys for the supplied TenantContext and prefix.
- The host injects a 32-byte AES key from secret management. The key is never stored in the database or repository.
- Every record uses a fresh 96-bit nonce. AES-GCM authenticated associated data binds ciphertext to tenant ID, subject ID, device ID and envelope version; moving a row across owners/devices fails authentication.
- Only ciphertext envelopes are stored. Endpoint URLs and subscription encryption keys are not written as plaintext by this adapter.
- This is an adapter, not a production backend. The existing local SQLite tenant storage correctly reports production_durable=False and is rejected. A real shared database backend must implement the contract and pass concurrency, backup, restore and isolation tests.
- Key rotation requires a deliberate re-encryption migration while the old key remains available; this adapter does not silently rotate or fall back to another key.

## Dependencies and remaining integration

Uses `cryptography` AESGCM. The runtime still needs to inject this store and a secret-manager key provider into `TenantPushSubscriptionRegistry` and `TenantWebPushNotificationSink`, then wire authenticated registration/revocation routes and a hosted outbox worker. No browser/service-worker or real-device delivery is claimed.