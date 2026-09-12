# SaaS production security baseline

The SaaS foundation is already provider-neutral and fail-closed. This document defines the additional deployment controls required before protected multi-tenant production use.

## Required controls

- trusted identity provider and authenticated subject/tenant context;
- tenant-isolated durable storage, including backup and recovery controls;
- HTTPS/TLS at the deployment boundary;
- managed secrets with no credentials committed to source or logs;
- durable security audit with tenant/request correlation and bounded sensitive data;
- centralized rate limiting suitable for multiple application instances;
- explicit authorization at every protected operation;
- fail-closed behavior when any required control is unavailable or unverifiable;
- REAL execution remains disabled.

These controls are provider-neutral. A deployment may use free, self-hosted, open-source, or commercial infrastructure; the core does not require a paid provider.

## Security boundary

The application core owns contracts, validation, tenant scoping, authorization decisions, and fail-closed behavior. Deployment infrastructure owns the concrete identity provider, durable database, TLS termination, secret store, durable audit sink, and distributed rate-limit implementation.

A deployment must not claim production multi-tenant readiness merely because the in-process development implementations are present.

## Permanent safety rule

Security is not considered a one-time checkbox. New integrations and features must preserve tenant isolation, least privilege, auditability, fail-closed behavior, and the REAL-disabled boundary.
