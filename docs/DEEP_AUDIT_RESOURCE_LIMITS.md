# Deep Audit — Limits and Capacity Classification

The ecosystem requirement is: no arbitrary functional/product capacity ceiling. A numeric value is not automatically a product limit; every bound must have an explicit reason tied to the resource or safety property it protects.

## Product/functionality

- Replay scenario count: **no artificial ceiling**. The previous 50-scenario cap was removed.
- SaaS plan quotas/counters: **removed**. Plans describe entitlements, not arbitrary numeric capacity counters.
- Memory/news query `limit`: pagination/presentation controls, not product capacity. The request value is validated for positivity and is not capped by a hidden maximum in the HTTP parser.

## Legitimate safety/resource controls

- HTTP request body size: protects process memory and request parsing resources.
- HTTP request rate/window: anti-abuse and availability protection.
- Tracked-client bound in the in-process limiter: protects local memory. It is not a product capacity promise.
- Security-event retention: bounded local operational cache. Centralized durable audit retention belongs to the production deployment boundary.
- Image payload size: protects upload/memory/storage resources.
- Market-data freshness thresholds: data-integrity/safety checks, not capacity.
- Trading risk limits such as daily loss, exposure, order amount, and operation counts: explicit risk controls and therefore intentionally retained. They are not product-capacity limits and must not be removed merely because they contain `max_*` fields.

## Production architecture rule

For multi-replica SaaS, local rate limiting and local operational retention are insufficient as the authoritative controls. A shared production mechanism must enforce the relevant anti-abuse/audit policy at the deployment boundary.

The system must never solve a resource problem by silently introducing a new arbitrary functional ceiling. When a response is too large, use pagination/cursors, streaming, asynchronous processing, cancellation, or another resource-aware mechanism instead of truncating functionality.
