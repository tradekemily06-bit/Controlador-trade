# Tenant Web Push component composition

`build_tenant_web_push_components` constructs the subscription registry and delivery sink over the same AES-GCM encrypted store. It accepts a durable tenant record backend and explicit secret-manager callbacks for the 32-byte encryption key and VAPID private key.

The returned `notification_sink` is the existing `StandaloneRuntime(tenant_notification_sink=...)` injection point; the runtime then owns and starts its outbox worker. The factory itself does not start a worker, open network listeners, or discover secrets.

Do not inject the components in the current default runtime until the host provides a real shared durable backend, key management and authenticated subscription routes. The runtime's present notification outbox and tenant state still use single-host SQLite, so this factory alone does not make the whole notification path multi-replica or production-ready.

Browser permission, service-worker subscription, authenticated POST/DELETE routes and real-device delivery validation remain separate required steps.