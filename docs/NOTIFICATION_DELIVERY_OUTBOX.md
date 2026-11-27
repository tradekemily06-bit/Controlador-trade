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

Important scope distinction: the legacy/shared ecosystem notification path can enqueue into
this outbox, but the tenant-scoped market/provider alert path currently writes to
the recipient's in-app tenant inbox through `TenantNotificationDispatcher` and
does not yet atomically enqueue the same event into an external-delivery outbox.
Therefore a new market signal, MT5/cTrader connection event, or TradingView alert
must not be described as delivered to a phone/browser outside the in-app inbox.
The missing work is a tenant-scoped transactional outbox in the same storage
transaction as the tenant inbox write, plus a tenant-aware delivery sink and
subscription/consent routing. Reusing the global outbox without that ownership
boundary would risk cross-tenant delivery and is intentionally not done.

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
