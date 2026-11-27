# cTrader OAuth refresh coordination

The OAuth refresh service supports an injected shared lease provider for deployments
with more than one worker or application replica.

## Contract

Inject `refresh_lease_provider` into `TenantCTraderOAuthService`. The provider
must expose:

```python
lease_provider.acquire(key, lease_seconds=90, wait_seconds=15)
```

The call must return either:
- a context manager that holds the lease until its context exits; or
- `None` when the lease cannot be acquired within the requested wait.

The key is scoped to tenant, subject, and connection. The lease must be atomic
across every application replica and must release safely on normal exit and
exceptions. Its backend should use server-side credentials and must not log
OAuth tokens or lease keys containing personal identifiers.

## Deployment rule

Without an injected shared lease provider, the service uses a process-local
thread lock. That fallback is suitable only for a single-process deployment.
It is **not** sufficient for multiple workers, containers, or hosts.

Do not enable multi-replica cTrader OAuth refresh in production until a shared
lease backend is configured and tested under concurrent refresh attempts.
A lease TTL must exceed the bounded token endpoint timeout, and the backend
must support safe expiry/recovery if a worker crashes. The current default
lease request is 90 seconds with a 15-second acquisition wait.

This mechanism coordinates token refresh only. It does not establish a cTrader
account session, prove DEMO mode, or authorize order execution. The integration
remains read-only.
