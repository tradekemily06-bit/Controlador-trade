# Tenant-scoped signal outcome persistence

`analysis/tenant_signal_outcome_store.py` joins the exact-timeframe directional resolver to a previously recorded signal audit. It requires the same `TenantSignalEvidenceStore` instance, so the signal and its result share one SQLite database.

## Guarantees

- A result can only be attached to a signal visible in the authenticated tenant/subject scope.
- The resolver validates the next immediate candle, symbol, timeframe, timestamps, validity window, OHLC consistency and real-market-data provenance.
- Only one outcome can be recorded per signal; subsequent resolution attempts are rejected.
- A doji remains unresolved rather than being forced into a win or loss.
- The result is explicitly marked as directional only; net profit is not assessed and probability of profit remains null.

## Still not production/live

This layer is callable by a future provider ingestion worker but is not yet invoked automatically by MT5/cTrader/TradingView ingestion. It does not authenticate the supplied `TenantContext`; trusted server-side identity middleware must provide that context. SQLite is still single-host development storage.

Before using outcomes for estimated profit or profit probability, the system still needs a verified executable-price model (bid/ask), position sizing, spread, commissions, slippage, latency, exit/invalidation rules, and out-of-sample validation. Directional candle labels must not be passed to the profit-probability evaluator.