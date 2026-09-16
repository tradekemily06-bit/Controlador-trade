# Deep Audit — Decision Ownership Boundary

## Purpose

Decision history is personal data in a multi-user SaaS. A trusted deployment identity must determine which subject and tenant may create, read, and mutate that history. Browser payloads must never be treated as proof of ownership.

## Current controls

- `DecisionRecord` carries `subject_id` and `tenant_id` ownership metadata.
- `ProductionTenantDecisionRepository` requires both `tenant_id` and `subject_id` for save/load/list operations.
- Production repository rejects records whose owner does not match the trusted scope.
- Production repository rejects stored records without valid ownership.
- Core decision fields are immutable after creation; outcome is the only mutable decision field.
- `EcosystemService` accepts trusted owner context for analysis, replay and outcome mutation.
- Partial owner context fails closed through `require_production_context`.
- Replay propagates one trusted owner to every generated record.
- `ConfiguredEcosystemService` preserves the same owner boundary instead of dropping ownership while applying senior-analysis gates.

## Important boundary

The current public SaaS HTTP mode remains fail-closed because the real tenant-scoped data plane and trusted authentication provider are not configured. This is intentional: the application must not expose the process-local/global foundation stores while claiming they are tenant-isolated.

The local/foundation mode retains backwards-compatible owner-optional service calls for tests and non-SaaS learning. Owner metadata becomes mandatory whenever a caller supplies production identity context.

## Next production wiring requirement

When the trusted SaaS data plane is enabled, the HTTP layer must obtain `subject_id`, `tenant_id`, and role only from the deployment/provider-injected trusted identity context, then pass that context into analyze/replay/outcome and all personal-data reads/writes. It must never accept these values from JSON or browser headers as authorization evidence.

No REAL execution authority is created by this ownership layer.
