# Tenant-scoped Web Push sink contract

The standalone tenant notification outbox can now be connected to a Web Push sender through TenantWebPushNotificationSink.

## Security contract

- The sink requires an injected subscription store that declares both production_durable=True and encrypted_at_rest=True. The local SQLite tenant store is deliberately not accepted as a production subscription vault.
- Each outbox delivery carries an explicit tenant_id and subject_id; the sink creates that exact owner context and reads only that owner's subscriptions. There is no broadcast or tenant enumeration.
- Persisted push endpoints are revalidated at send time against the browser push-service HTTPS host allowlist. This prevents stored data from becoming an SSRF destination.
- Only public notification fields are serialized. Internal metadata and arbitrary payload fields are excluded; payloads are capped at 3,500 UTF-8 bytes.
- The outbox idempotency key is included in the payload so a service worker can deduplicate at-least-once delivery.
- Confirmed HTTP 404/410 responses remove only the matching owner's expired device subscription. Other provider failures are raised as a generic redacted exception so the outbox retries without persisting endpoint tokens or provider response bodies.
- The injected sender owns VAPID signing, payload encryption and HTTPS transport. Its callback contract is sender(subscription_info, payload_json, ttl_seconds=..., idempotency_key=...). VAPID private keys must remain in host secret management and must never be stored in the repository or browser.

## What remains before real device delivery

This is the backend delivery boundary, not proof of push delivery. Production still needs a real durable encrypted subscription-store adapter, a VAPID-backed sender implementation, authenticated subscribe/revoke HTTP routes, browser permission and service-worker registration, hosted worker continuity, and an end-to-end test on an actual browser/device. The Lovable UI is not modified by this backend change.

The default standalone runtime still injects no tenant notification sink. Until the host configures the complete path and verifies delivery, status must continue to report external delivery as disabled/outbox-only.