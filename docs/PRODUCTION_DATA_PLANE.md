# Production data plane

The public SaaS path must never use the process-local `DecisionStore` as a tenant database.

## Required environment

```text
CONTROLADOR_SAAS_PUBLIC=true
CONTROLADOR_PRODUCTION_STORE=sqlite
CONTROLADOR_PRODUCTION_DB=/data/controlador-production.sqlite3
CONTROLADOR_MULTI_INSTANCE=false
```

This configuration enables a durable tenant+subject-scoped SQLite provider for a **single application instance**. It is suitable for controlled single-node deployment/testing, not horizontal SaaS scaling.

## Multi-instance rule

`CONTROLADOR_MULTI_INSTANCE=true` rejects SQLite at startup/configuration time. A shared provider implementing the `TenantScopedDecisionProvider` contract is required before multiple application instances can safely share production state.

The application must not silently downgrade to in-memory state when the provider is absent or unavailable.

## Scope invariant

Every production decision read/write requires both:

- trusted `tenant_id`
- trusted `subject_id`

The values must originate from the server-injected trusted identity boundary, not browser-controlled headers or request payloads.

## State covered by the decision data plane

The durable path is the source of truth for:

- analysis decisions;
- replayed decisions;
- outcomes;
- memory views;
- statistics;
- historical psychology analysis derived from decisions.

Psychology remains a parallel behavioral-protection layer and never gains decision or execution authority.

## Failure behavior

- provider absent in public SaaS: fail closed;
- incomplete tenant/subject scope: reject;
- provider returns another scope: fail closed;
- SQLite declared multi-instance: reject;
- local/test mode without public SaaS: existing local `DecisionStore` behavior remains available.
