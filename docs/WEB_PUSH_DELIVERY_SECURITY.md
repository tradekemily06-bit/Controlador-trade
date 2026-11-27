# Web Push delivery security and activation contract

This document defines the production gate for enabling Web Push. It does not enable delivery or authorize network requests.

## Trust boundaries

- A browser-provided subscription endpoint is untrusted input. HTTPS syntax validation alone is not sufficient authorization to make an outbound request.
- The sender MUST validate the endpoint hostname against the supported push-service provider policy and resolve DNS immediately before each delivery attempt.
- The sender MUST reject loopback, private, link-local, multicast, reserved, unspecified and otherwise non-public destination addresses for both IPv4 and IPv6. Reject mixed DNS answers if any answer is prohibited.
- The sender MUST defend against DNS rebinding by connecting to a validated resolved address while preserving the expected TLS hostname/SNI and certificate verification.
- Redirects MUST be disabled. If a provider requires redirects, each redirect target must be independently revalidated under the same DNS/IP policy, with a strict small hop limit. Never forward VAPID authorization headers across origins.
- Enforce connect/read timeouts, response-size limits, bounded concurrency, per-owner/device rate limits and an overall delivery deadline.
- Never fetch arbitrary URLs from notification payloads, user content, RSS articles or assistant output.

## Subscription and cryptographic material

- Subscription endpoints, p256dh keys and auth secrets are credentials. Store them encrypted at rest using a managed key-encryption design with rotation and access auditing.
- VAPID private keys and signing credentials belong in a deployment secret manager, never in source control, frontend bundles, logs, database plaintext or API responses.
- Keep VAPID subject/contact metadata configured and validate key-pair consistency before enabling delivery.
- The browser may register or revoke only its own device subscription after trusted tenant-and-subject authentication. Device IDs are record keys, never identity claims.
- List/status APIs may return opaque device IDs, status and bounded timestamps only; never return endpoints or cryptographic keys.

## Tenant isolation and payload minimization

- Resolve the owner from trusted server-side identity for every registration, listing, revocation and delivery operation.
- Select subscriptions only from the authenticated owner's storage partition. Never accept tenant IDs or subject IDs from a request body as authority.
- A notification's outbox owner must match the subscription owner before dispatch.
- Push payloads should contain only a generic notification identifier and minimal display text. Do not include balances, fiscal records, conversation text, market positions, broker credentials or private analysis context.
- The application must continue to provide an authenticated in-app inbox when Push is unavailable, denied or unsupported.

## Delivery semantics

- Treat delivery as at-least-once. Use a stable outbox idempotency key and tolerate duplicate browser notifications.
- Confirmed HTTP 404/410 may retire only the exact subscription belonging to the notification owner. Other 4xx responses must be classified; 401/403 must not trigger broad deletion.
- Retry 429 and transient 5xx/network failures with bounded exponential backoff and jitter, honoring a valid bounded Retry-After value.
- Do not retry permanent validation failures indefinitely. Move exhausted attempts to a tenant-isolated dead-letter state with redacted diagnostics.
- Record status codes, latency and retry counts, but redact endpoint paths, authorization headers, payload secrets and subscription keys from logs and traces.

## Required release gates

1. Production-durable encrypted subscription storage is deployed and tested for tenant/subject isolation, key rotation, backup and restore.
2. VAPID secrets are provisioned through a secret manager and rotation is tested.
3. SSRF-resistant endpoint authorization and redirect handling pass IPv4/IPv6, DNS rebinding, private-address and mixed-answer tests.
4. The sender enforces TLS verification, timeouts, payload limits, rate limits, bounded retries and redacted telemetry.
5. Outbox ownership is checked against subscription ownership at dispatch time; duplicate and concurrent delivery tests pass.
6. Browser registration/revocation routes use trusted identity and CSRF/origin protections appropriate to the deployed authentication model.
7. Android and iOS physical-device tests cover permission denial, revocation, expired subscriptions, offline/reconnect and notification clicks.
8. Hosted worker continuity is proven across process restart and deployment replacement; local process-lifetime workers are not sufficient.
9. In-app inbox behavior remains correct when Push is disabled.
10. A security review and full CI pass are required before enabling the sender in any production environment.

## Current implementation boundary

The current code provides only the tenant-scoped subscription registry contract. It does not implement the sender, endpoint DNS policy, VAPID management, production encrypted storage, registration routes, browser permission flow, hosted worker or physical-device acceptance. Push remains disabled.