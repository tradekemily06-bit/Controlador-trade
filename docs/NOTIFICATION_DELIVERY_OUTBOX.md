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

The tenant-scoped market/provider alert path now writes the in-app inbox and
`tenant_notification_outbox` in the same SQLite transaction. The outbox is
partitioned by tenant, subject and notification ID; its worker sends the exact
recipient identity to a tenant-aware sink, uses collision-resistant idempotency
keys, lease ownership, retries, and dead-letter handling. The tenant notification
status endpoint reports only the authenticated owner's outbox counts and worker
state. A local tenant outbox cannot be claimed or delivered by another owner.

The tenant-aware worker is an optional runtime dependency:
`StandaloneRuntime(tenant_notification_sink=...)`. The default environment
still supplies no sink, so external delivery remains disabled and status reports
`NO_TENANT_EXTERNAL_SINK_CONFIGURED` / `OUTBOX_ONLY_NO_PROVIDER`. The worker
and queue are now connected, but a real tenant-aware delivery adapter, consented
device-subscription storage, VAPID credentials, browser/PWA lifecycle and
end-to-end phone/browser delivery test remain required. Never describe an event
as delivered merely because it is present in the outbox or the worker is running.

This tenant outbox shares `tenant-state.sqlite3`, which is included in the
allowlisted local SQLite backup. It remains single-host development storage;
multi-replica production still requires a shared transactional database and
distributed lease fencing.

No provider credentials or user subscription data are stored in source code.
The delivery adapter must be configured server-side and must never authorize
trading or money movement.


## Standalone notification API

The standalone HTTP API exposes the persisted in-app inbox without changing
the approved frontend layout:

- `GET /api/notifications?limit=50&include_info=false` returns the newest
  visible notifications (including current read-only operational incidents).
  The limit is bounded from 1 to 200.
- `GET /api/notifications/status` reports notification persistence, outbox
  counts, and whether an external delivery worker was injected and is running.

These endpoints use the same standalone access boundary as the other app
endpoints. They do not mark items as read and do not create push subscriptions.
A configured worker still needs a real delivery sink; merely having queued
notifications or a running worker is not proof that a browser or phone received
them. Mobile and desktop use the same tenant-scoped inbox and API. Phone delivery while the browser is closed is not enabled yet: it requires the frontend PWA service worker, per-device subscription lifecycle, server-side tenant-scoped subscription storage, VAPID credentials, a real Web Push sender, hosted worker continuity, and device-level end-to-end validation. Do not treat a queued outbox item as a delivered push notification.
