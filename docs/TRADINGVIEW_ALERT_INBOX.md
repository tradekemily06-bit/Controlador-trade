# TradingView alert inbox (read-only foundation)

The TradingView integration is deliberately split from broker candle adapters.

## What this service does

- Accepts one alert event for a tenant-owned `tradingview_webhook` connection.
- Resolves webhook secrets to a server-owned tenant, subject and connection.
- Rejects wrong secrets, stale/future timestamps, oversized payloads, invalid symbols/intervals/actions and replayed event IDs.
- Persists only normalized alert fields; the secret and arbitrary payload fields are not stored.
- Isolates event history by tenant, subject and connection.
- Returns `read_only=true` and `execution_authorized=false`.

## Provisioning and public route

The authenticated application endpoint `POST /api/market-data/tradingview-webhook-connections` accepts only `account_alias`. The server creates a pending connection, generates a high-entropy webhook secret, stores only its SHA-256 hash, and reveals the secret once. The response includes `endpoint_path`.

The public endpoint is `POST /api/webhooks/tradingview/{connection_id}` and requires HTTPS. The JSON body includes the secret and alert fields. The secret resolves to a trusted tenant/subject/connection in the server vault; the URL connection ID must match that result. The first valid alert promotes the connection to CONNECTED. Deleting the connection revokes its secret.

Expected JSON fields:
- `secret`: one-time secret issued during onboarding
- `event_id`: unique event identifier
- `ticker`: symbol/ticker
- `interval`: TradingView interval
- `action`: `BUY`, `SELL`, `WAIT`, or `ALERT`
- `fired_at`: ISO 8601 timestamp with timezone
- `price`: optional positive number

The authenticated history endpoint is `GET /api/market-data/connections/{connection_id}/tradingview-alerts?limit=50` (limit 1–200). Accepted alerts are also routed to the owning tenant's notification dispatcher; downstream delivery still depends on a configured notification sink/worker.

## Important limitation

A TradingView webhook is an alert delivery, not a continuous market-data or candle stream. It must not be represented as a live broker feed or used by itself to claim that every timeframe is current. Continuous analysis still requires a supported broker/exchange market-data adapter or another verified candle source.

## Deployment requirements

- Publish the public route only behind HTTPS.
- Configure request-size limits, rate limits, monitoring and alert-delivery observability at the host.
- Keep the one-time secret out of the Lovable frontend source, logs, analytics and support tickets.
- Test an actual TradingView alert delivery against the deployed endpoint before marking the integration production-ready.

No orders or money movement are supported.
