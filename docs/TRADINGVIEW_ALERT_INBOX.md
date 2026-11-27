# TradingView alert inbox (read-only foundation)

The TradingView integration is deliberately split from broker candle adapters.

## What this service does

- Accepts a single alert event for a verified, tenant-owned `tradingview_webhook` connection.
- Resolves the expected webhook secret server-side for that exact tenant and connection.
- Rejects wrong secrets, stale/future timestamps, oversized payloads, invalid symbols/intervals/actions and replayed event IDs.
- Persists only a normalized allowlist of alert fields; the secret and arbitrary user-supplied fields are not stored.
- Isolates event history by tenant, subject and connection.
- Returns `read_only=true` and `execution_authorized=false`.

## Important limitation

A TradingView webhook is an alert delivery, not a continuous market-data or candle stream. It must not be represented as a live broker feed or used by itself to claim that every timeframe is current. Continuous analysis still requires a supported broker/exchange market-data adapter or another verified candle source.

## Host integration still required

The service is a backend primitive and is not yet exposed as a public webhook route. Before enabling it, the host must provide:
1. A trusted mapping from each webhook URL/secret to one tenant and one connection (never accept tenant IDs from the payload).
2. A server-side secret resolver backed by the deployment's secret manager.
3. An HTTPS-only, rate-limited route with request-size limits and monitoring.
4. A real TradingView alert delivery test against the deployed endpoint.

Do not reuse the MT5 relay bearer token as a TradingView webhook secret. No orders or money movement are supported.
