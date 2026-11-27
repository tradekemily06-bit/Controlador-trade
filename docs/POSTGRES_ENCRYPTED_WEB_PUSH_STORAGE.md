# Shared encrypted Web Push subscription storage

PostgresEncryptedPushSubscriptionStore is the durable-storage adapter for the tenant Web Push registry. It uses a host-injected PostgreSQL connection factory and AES-256-GCM application-layer encryption.

## Security and deployment contract

- The connection factory must be a trusted host object that explicitly declares shared_database=True and production_durable=True. This is an operator attestation, not automatic proof that the database is correctly configured.
- Use a managed/shared PostgreSQL service with TLS verification, private networking, least-privilege credentials, backups, restore tests and monitoring. Do not point this adapter at SQLite or a local file.
- The encryption-key provider must return exactly 32 bytes for the requested key version. It is called at composition and for each read/write; the store does not retain key material.
- Keep the AES key in the host KMS/secret manager. Never put it in Lovable, browser code, environment files committed to Git, logs or API responses.
- Endpoint and Web Push encryption keys are encrypted together with AES-256-GCM. Tenant ID, subject ID, device ID and key version are authenticated as additional data, so moving ciphertext between owners or devices fails authentication.
- Only owner identifiers and opaque device metadata remain queryable in plaintext. There is no tenant enumeration or broadcast API.
- initialize_schema() is an explicit deployment migration step and should run using a migration identity. The runtime role should receive only the minimum required table privileges.
- Keep old key versions available for decryption during rotation. A rotation job must decrypt and re-encrypt each owner's rows under the new key version before the old key is retired. Do not simply replace the provider's current key.

## Runtime composition

Create one store instance with the trusted PostgreSQL factory and versioned KMS callback. Call build_tenant_web_push_components(store, vapid_private_key_provider, subject=...) to receive the registry and sink sharing that exact store. Inject the resulting registry as tenant_push_subscription_registry and sink as tenant_notification_sink into StandaloneRuntime. The existing WSGI app mounts the authenticated GET/POST/DELETE routes when the registry is present, and the existing tenant outbox worker starts only when the sink is injected.

The frontend still needs the browser assets deployed on its own HTTPS origin. The existing Lovable notification settings can call the behavior-only helper; no new UI is required.

## What this does not prove

The adapter and automated tests do not provision a database, KMS key, VAPID key pair, hosted runtime, or browser deployment. They do not establish multi-replica readiness for the rest of the application: the current standalone runtime still uses local SQLite for other state and enforces its single-replica topology guard. A continuously running hosted worker, configured secrets, database restore validation and real-device end-to-end tests remain mandatory before external delivery can be called operational. Web Push itself is best-effort, not a guaranteed alert channel.
