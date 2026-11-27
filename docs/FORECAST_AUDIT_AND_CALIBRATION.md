# Forecast audit and probability calibration

## Purpose

A probability is eligible for later statistical evaluation only when the forecast
was persisted before its outcome was known. A technical-strength score is not a
probability and must never be copied into the probability field.

## Current implementation

- \`analysis/tenant_forecast_audit_store.py\` records a forecast before resolution.
- Records are scoped by tenant and subject and keyed by a forecast ID.
- Symbol, direction, model version and canonical timeframe are retained.
- Resolution is immutable and must occur after the forecast timestamp.
- Only \`REAL_MARKET_DATA\` and \`VERIFIED_REAL_EXECUTION\` provenance are eligible.
- Manual labels and simulated DEMO fills are rejected as calibration outcomes.
- \`analysis/probability_calibration.py\` evaluates only out-of-sample records and
  groups independently by symbol, timeframe, direction and model version.
- Brier score, log loss, reliability bins, confidence intervals and expected
  calibration error are diagnostics. They do not automatically approve a model
  or publish a win probability.

## Separate signal-direction evidence pipeline

A distinct pipeline now records actionable signal evidence and checks the
immediately following closed candle. It is implemented by
`analysis/tenant_signal_evidence_store.py`,
`analysis/tenant_signal_outcome_store.py` and
`analysis/signal_outcome_resolver.py`, and is wired into the standalone
analyzer for explicitly allowlisted MT5 relay/DEMO and cTrader Open API
sessions. Each record is isolated by tenant, subject, provider connection,
symbol and canonical timeframe. Only COMPRA/VENDA signals receive directional
outcomes; AGUARDAR is not a directional label. A doji remains unresolved.

This measures only whether the next candle moved in the predicted direction.
It does **not** establish net profitability, an executable entry/exit, or a
probability of profit. The probability-forecast audit store below remains a
separate facility: no genuine probability-producing model currently feeds it,
so the public probability must remain `NOT_CALIBRATED`. Do not copy technical
evidence scores or directional hit rates into the probability field.

## Important limitations

This store currently uses local SQLite. It is a single-host development
foundation, not the shared transactional database required for multi-replica
production. The trusted \`TenantContext\` must be supplied by authenticated
server-side middleware; constructing the value object is not authentication.

The store is not yet wired into the live standalone analyzer or a provider
outcome resolver. No live forecast is automatically persisted by this change.
Until the end-to-end capture and resolution pipeline is connected and tested,
the product must continue to report probability as \`NOT_CALIBRATED\`.

Real market candles may validate market-price outcomes in DEMO or REAL mode.
That does not validate actual execution quality. Slippage, fees, spreads,
partial fills and broker-specific execution outcomes require separate verified
execution evidence.

## Required next integration steps

1. Implement and validate a genuine probability-producing model, then persist its forecast atomically before any outcome is available. Do not convert the technical evidence score or directional candle labels into probabilities.
2. Define an outcome resolver with explicit entry/exit and invalidation rules,
   candle-source identity, and conservative handling when stop and target occur
   inside the same candle.
3. Resolve forecasts only from complete, fresh, time-ordered market data;
   record source and resolution timestamp.
4. Add walk-forward evaluation and temporal holdout. Prevent overlap between
   training, calibration and evaluation windows.
5. Review sample sufficiency, confidence intervals, regime stability and
   transaction costs separately for every symbol/timeframe/direction/model.
6. Keep public probability unavailable until a separate, reviewed approval
   policy explicitly promotes the calibrated model.

No order execution is implemented or authorized by this subsystem.
