# Security deployment contract

## Server-side authentication

Production must set:
- `CONTROLADOR_ENV=production`
- `CONTROLADOR_AUTH_USERNAME`
- `CONTROLADOR_AUTH_PASSWORD_HASH` (scrypt hash only; never plaintext)
- `CONTROLADOR_SESSION_SECRET` (random server secret)
- `CONTROLADOR_REQUIRE_HTTPS=true`

Generate a password hash without writing the password to source:

```bash
python -m security.generate_password_hash
```

The browser receives only an opaque HttpOnly/SameSite session cookie. Session state and the CSRF token remain server-side. State-changing requests require the CSRF header.

## Secrets

Broker/API credentials belong in the deployment secret manager or server environment. They must never be embedded in frontend JavaScript, source, Docker images, logs, URLs, or Git history.

The current repository contains no `.env`, service-role key, private key, or provider API key found by the repository code searches performed in this audit.

## Database

The current decision/security persistence uses SQLite and therefore has no database API key or PostgreSQL RLS primitive to expose. Do not add a Supabase `service_role` key to frontend code. If/when a hosted Postgres/Supabase backend is introduced, the browser may receive only the public/anon key and every tenant-owned table must have RLS policies; privileged server keys stay server-side.

## Input, uploads and output

JSON bodies are size-limited, reject duplicate keys, reject NaN/Infinity, bound nesting/field/list sizes, and reject multipart uploads because the application currently has no upload feature.

Responses use security headers and production health output is minimized. User-controlled HTML is escaped in the current dashboard.

## TLS, cookies and rate limits

Production HTTPS enforcement adds HSTS and Secure cookies. The application already has a bounded in-process request rate limiter; authentication adds a separate failed-login limiter. A multi-instance deployment must use a centralized rate limiter.

## Supply chain

CI already runs `pip-audit`. The repository currently has no `uv.lock`; the supply-chain auditor should be run against a generated/frozen uv resolution once uv is introduced. Keep GitHub Actions pinned to full commit SHAs.

## Remaining deployment controls

- enable GitHub Secret Protection / push protection;
- rotate any credential if GitHub reports a historical leak;
- terminate TLS at the deployment boundary;
- use a managed secret store;
- use durable encrypted storage for sensitive production records;
- use tenant-aware database policies/RLS when a multi-tenant Postgres backend is introduced.
