# Technical signal evidence audit

`analysis/tenant_signal_evidence_store.py` records the exact technical decision emitted by the analyzer without treating its score as a win probability.

## Recorded evidence

Each immutable row is scoped by tenant and subject and captures:

- signal ID, provider/account source identity, symbol, canonical timeframe, direction and model version;
- technical evidence score from 0 to 100;
- explicit score meaning: `EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY`;
- closed-candle timestamp, analysis observation timestamp and signal expiry;
- real-market-data provenance.

M1 and M5 are stored and queried independently. A record is rejected if analysis predates the closed candle, if expiry is not in the future, if the score semantics are ambiguous, or if provenance is manual/simulated rather than real market data.

## Separation from probability calibration

This is not a probability forecast store and its records must never be passed to the probability evaluator. The score answers only how strong the analyzer's technical evidence was at that moment. It does not answer the probability of profit.

The probability audit store remains a separate path and accepts explicit probability forecasts only when a real probability-producing model exists. No probability is inferred from this evidence score.

## Current limitations

- SQLite is local, single-host development storage; it is not production multi-tenant infrastructure for multiple replicas.
- The standalone analyzer now records fresh signal decisions for configured MT5 relay, MT5 DEMO and cTrader adapters. Tenant sessions use their unique connection ID as source identity. The same runtime resolves the prior actionable signal against the exact next closed candle; AGUARDAR decisions are not classified as directional wins or losses. Reprocessing the same closed candle after restart is idempotent: an identical evidence row is acknowledged as `ALREADY_RECORDED`, while reusing its ID with different evidence is rejected.
- The `REAL_MARKET_DATA` tag is assigned by the runtime to the configured adapter classes; it is not independent proof that a live provider session, exchange timestamp, or feed entitlement was verified. Real MT5/cTrader account handshakes and live-feed acceptance still require external integration tests.
- `TenantContext` is a value object, not authentication. Only trusted server-side identity middleware may construct it.
- No outcome is inferred here. A separate outcome resolver must define entry/exit, expiry, spread/cost treatment, and conservative handling of ambiguous candles before any signal performance statistics are produced.
- No broker order execution or money movement is added.