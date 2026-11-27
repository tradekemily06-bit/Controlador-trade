# Tenant-scoped signal outcome persistence

`analysis/tenant_signal_outcome_store.py` joins the exact-timeframe directional resolver to a previously recorded signal audit. It requires the same `TenantSignalEvidenceStore` instance, so the signal and its result share one SQLite database.

## Guarantees

- A result can only be attached to a signal visible in the authenticated tenant/subject scope.
- The resolver validates the next immediate candle, symbol, timeframe, timestamps, validity window, OHLC consistency and real-market-data provenance.
- Only one outcome can be recorded per signal; subsequent resolution attempts are rejected.
- A doji remains unresolved rather than being forced into a win or loss.
- The result is explicitly marked as directional only; net profit is not assessed and probability of profit remains null.

## Still not production/live

The standalone runtime now invokes this resolver during a fresh closed-candle analysis for explicitly allowlisted MT5 relay, MT5 DEMO and cTrader market-data sessions. Each tenant connection is assigned its own source identity, so one account's candle cannot resolve another account's signal. Only an actionable COMPRA/VENDA from the immediately preceding candle is resolved; AGUARDAR is retained as evidence but excluded from directional hit/miss labels. TradingView webhook events are not treated as candle data. It does not authenticate the supplied `TenantContext`; trusted server-side identity middleware must provide that context. SQLite is still single-host development storage.

Before using outcomes for estimated profit or profit probability, the system still needs a verified executable-price model (bid/ask), position sizing, spread, commissions, slippage, latency, exit/invalidation rules, and out-of-sample validation. Directional candle labels must not be passed to the profit-probability evaluator.