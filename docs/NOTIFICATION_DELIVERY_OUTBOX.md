# Persistent notification delivery outbox

The standalone runtime now records newly published ecosystem notifications in a
SQLite outbox in addition to the in-app notification store.

## Current behavior

- Each notification is queued with its `notification_id` as an idempotency key.
- The outbox stores the payload, delivery state, attempt count, lease, retry
  time, delivery receipt, and last error.
- A worker claims due messages atomically, then marks successful deliveries or
  schedules exponential retries.
- Expired in-flight leases can be reclaimed after a worker interruption.
- Messages exceeding the configured attempt limit move to the `DEAD` state.
- The outbox is at-least-once: a destination must deduplicate using the supplied
  idempotency key to handle a crash after remote acceptance but before the
  local receipt is committed.

## What is not enabled yet

This is durable queue infrastructure, not a live push service. A transport-neutral
background worker is now available and is started only when a configured sink is
explicitly injected into `StandaloneRuntime(notification_sink=...)`. The default
environment startup still supplies no sink, so the API reports
`OUTBOX_ONLY_NO_PROVIDER`. No notification is claimed to reach a phone or
browser while the application is closed until a real provider, subscription
management, production worker configuration, and end-to-end device delivery test
are configured.

No provider credentials or user subscription data are stored in source code.
The delivery adapter must be configured server-side and must never authorize
trading or money movement.
