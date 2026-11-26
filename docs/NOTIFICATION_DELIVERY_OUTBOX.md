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

This is durable queue infrastructure, not a live push service. The standalone
runtime currently creates the outbox but does not configure a delivery sink or
start a background worker. The API therefore reports
`OUTBOX_ONLY_NO_PROVIDER`. No notification is claimed to reach a phone or
browser while the application is closed until a real provider, subscription
management, worker lifecycle, and end-to-end delivery test are configured.

No provider credentials or user subscription data are stored in source code.
The delivery adapter must be configured server-side and must never authorize
trading or money movement.
