# SaaS identity boundary

The SaaS identity boundary is provider-neutral. A trusted deployment identity provider supplies an authenticated subject, tenant, and role; the application converts that identity into `TenantContext`.

This layer does not implement passwords, sessions, tokens, browser-header authentication, tenant discovery, billing, or live broker execution.

Missing or malformed trusted identity fails closed. A production deployment must connect this contract to its chosen identity provider before protected multi-tenant operations are enabled.
