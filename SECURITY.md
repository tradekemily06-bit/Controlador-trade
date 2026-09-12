# Security Policy

## Scope

Controlador-trade is designed with a fail-closed security model and keeps REAL/live execution disabled by default.

## Reporting a vulnerability

Do **not** publish credentials, tokens, private keys, broker account details, personal data, or a working exploit in a public issue.

For vulnerabilities affecting users, production deployments, tenant isolation, authentication, secrets, or trading/execution safety, use GitHub's private vulnerability reporting/security advisory mechanism when enabled. If unavailable, contact the repository owner privately through GitHub before public disclosure.

Include the affected component, reproducible steps or a safe proof of concept, impact, realistic attack conditions, and any known mitigation.

## Security expectations

- REAL/live execution must remain disabled unless a separately reviewed production design explicitly changes that policy.
- New integrations must preserve fail-closed behavior, least privilege, tenant isolation, auditability and explicit environment separation.
- Secrets must never be committed to the repository or embedded in source code, tests, fixtures, logs or documentation.
- DEMO credentials and broker configuration must be treated as sensitive.
- Tests must not require real credentials or real-money execution.
- Security claims must distinguish implemented controls from deployment prerequisites.

## Current posture

The repository contains provider-neutral SaaS security boundaries, tenant-scoped persistence/audit controls, execution safety boundaries, API hardening, automated security checks and a production security baseline. Trusted production identity, durable multi-instance storage, secure transport, secret management and centralized rate limiting remain deployment prerequisites rather than guarantees provided by an in-process development environment.

## Disclosure principle

Security fixes should be developed privately when public disclosure would materially increase risk. After a fix is available, disclosure should provide enough information for users to protect themselves without exposing credentials or unnecessarily weaponizing the vulnerability.
