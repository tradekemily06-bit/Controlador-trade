# Multi-replica market-data deployment boundary

## Current supported topology

The standalone market-data runtime currently uses SQLite for tenant-scoped provider connection metadata, candle-close watch subscriptions and analysis results, processing leases and notification outbox rows, and OAuth state/token metadata (ciphertext only for tokens).

The timeframe processing lease and notification outbox coordinate correctly only when all workers access the same SQLite database file on storage with SQLite-compatible locking semantics. A local process lock also prevents two standalone runtime owners from opening the same runtime directory concurrently.

This is a single-host / single-runtime deployment boundary. Do not scale the application by starting multiple containers with separate local volumes and assume duplicate work or notification delivery is coordinated.

## Required before multi-host / multi-replica production

1. Move tenant metadata, watch subscriptions, results, processing leases and notification outbox to one shared transactional database (recommended: PostgreSQL).
2. Keep tenant and subject identifiers in every ownership predicate. Use database row-level security where practical, but retain application-level trusted-context checks.
3. Acquire a processing lease atomically using a unique watch key and an expiring owner token. Renew only while the same token owns an unexpired lease. Fence result persistence in the same transaction that inserts the result and outbox event.
4. Claim outbox rows transactionally with PostgreSQL `FOR UPDATE SKIP LOCKED` (or an equivalent atomic claim). Persist attempt count and lease expiry. Keep stable event IDs and require downstream deduplication because delivery is at-least-once, not exactly-once.
5. Use a distributed lease backend for cTrader OAuth refresh. The current injected lease-provider contract must be backed by the same shared coordination service across all replicas.
6. Move encrypted OAuth ciphertext and key metadata to durable shared storage; keep the encryption key in KMS/envelope encryption, never in the database or repository.
7. Ensure provider stream ownership is explicit. A replica restart must rehydrate subscriptions safely, and only one active stream owner per tenant/account/symbol/timeframe should publish accepted closed candles.
8. Add graceful worker shutdown, lease expiry recovery, database failover tests, and concurrent multi-replica tests before enabling horizontal scaling.

## Release gates

A multi-replica release is blocked until automated integration tests prove:
- two independent app replicas cannot analyze the same closed candle concurrently;
- a worker that loses its lease cannot persist a result or create an outbox event;
- a crashed worker's lease expires and another worker safely resumes;
- concurrent outbox consumers do not claim the same event simultaneously;
- retries preserve the same event ID and do not lose the durable analysis;
- tenant A cannot read, renew, release, or dispatch tenant B's work;
- OAuth refresh rotation is serialized across replicas;
- health/readiness reports a missing shared backend as unavailable rather than silently falling back to local coordination.


## Local backup coverage

The allowlisted on-demand SQLite backup set includes
`tenant-connection-timeframe-monitor.sqlite3`, which contains tenant-scoped
candle watches, analysis results, processing leases and notification outbox
records, and `tenant-tradingview-alerts.sqlite3`, which contains accepted
TradingView alert history. These stores must be backed up together with tenant
metadata; omitting them would lose active monitoring state, pending tenant
notifications or accepted alert history during recovery.

Backups remain local/on-demand unless an operator separately configures a
scheduled job and off-host replication. OAuth state, OAuth ciphertext, relay
tokens and webhook secret stores are not implicitly copied by this allowlist;
recovery procedures must account for provider re-authentication and key
availability rather than assuming those credentials can be reconstructed.
A successful isolated restore check validates SQLite integrity only; it does
not prove full application recovery or multi-host disaster recovery.

## Current product safety

Provider adapters remain read-only. A connected account is not considered operational until its provider handshake and fresh market data are verified. TradingView webhooks are event alerts, not continuous price feeds. A local MT5 relay requires its host terminal and machine to remain online. Closing the app window is not equivalent to shutting down the always-on worker host.

SIMULAÇÃO remains the default. Real order execution and money movement are outside this foundation and remain disabled.
