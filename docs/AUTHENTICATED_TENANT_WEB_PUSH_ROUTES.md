# Authenticated tenant Web Push routes\n\n`TenantPushSubscriptionWSGI` provides a mountable WSGI route component:\n\n- `GET /api/push/subscriptions` — list only device IDs/status/expiry for the authenticated tenant+subject.\n- `POST /api/push/subscriptions` — register/rotate one browser subscription.\n- `DELETE /api/push/subscriptions/{device_id}` — revoke one owner-local device.\n\n## Security boundary\n\nThe route does not accept tenant or subject IDs from request bodies, query strings or arbitrary identity headers. The host must inject `context_resolver`, backed by its already-authenticated server-side session/JWT/identity middleware, and `mutation_authorizer`, which must enforce the deployment's CSRF/origin policy for cookie-authenticated POST/DELETE requests. Missing/invalid identity returns 401; failed mutation authorization returns 403. Responses are `no-store` and do not disclose endpoint URLs or subscription encryption keys.\n\nThe route component returns `None` for unrelated paths. It is mounted automatically by `StandaloneWSGIApplication` when the host injects `tenant_push_subscription_registry` into `StandaloneRuntime`. Build matching registration/delivery components with `build_tenant_web_push_components`, then pass its `subscription_registry` as `tenant_push_subscription_registry` and its `notification_sink` as `tenant_notification_sink` when constructing the runtime. The standalone API first enforces its existing bearer-token and trusted-identity boundary; exact-origin CORS is already applied by the host. The standalone API does not use ambient cookie authentication, so the mutation callback relies on that bearer-token gate rather than a cookie CSRF token. If a deployment changes to cookie sessions, it must add CSRF protection before enabling mutations.\n\n## API payload\n\nPOST body shape: `{ "device_id": "browser-1", "subscription": { "endpoint": "https://…", "keys": { "p256dh": "…", "auth": "…" }, "expirationTime": null } }`.\n\nBody limit is 8 KiB. Endpoint host, HTTPS, P-256 public key and 16-byte auth secret are validated by the registry. The endpoint itself and keys are stored encrypted. The host still needs a concrete production durable backend, real secret manager, service worker, browser permission UX and real-device delivery tests. No production delivery is claimed.

## Standalone runtime wiring

```python
from security.postgres_encrypted_push_subscription_store import (
    PostgresEncryptedPushSubscriptionStore,
)

# Run initialize_schema() separately as a deployment migration.
subscription_store = PostgresEncryptedPushSubscriptionStore(
    postgres_connection_factory,
    secret_manager.get_push_encryption_key,
    key_version="push-subscriptions-v1",
)
subscription_registry, notification_sink = build_tenant_web_push_components(
    subscription_store,
    secret_manager.get_vapid_private_key,
    subject="mailto:ops@example.com",
)
runtime = StandaloneRuntime(
    tenant_push_subscription_registry=subscription_registry,
    tenant_notification_sink=notification_sink,
)
application = StandaloneWSGIApplication(runtime)
```

This is an explicit host composition example, not a claim that the repository currently has a concrete shared durable backend or secret-manager implementation. The current default environment factory does not enable push delivery.
