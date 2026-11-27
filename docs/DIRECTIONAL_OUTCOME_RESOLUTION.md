# Directional outcome resolver

`analysis/signal_outcome_resolver.py` resolves a signal against exactly one subsequent candle of the same symbol and canonical timeframe.

## Strict matching

- The outcome candle must open exactly at the signal candle's close boundary.
- The symbol and timeframe must match; M1 cannot use M5 data, and no later candle may silently substitute for the immediate next candle.
- The next candle must close before the signal validity expires.
- Only `REAL_MARKET_DATA` provenance is accepted.
- OHLC consistency and finite numeric values are checked.
- A doji is `UNRESOLVED_DOJI`, not a win or loss.

## What this label means — and does not mean

The label compares the next candle's close with its open in the signal direction. It is a directional hit/miss diagnostic only. It does not model executable entry price, spread, commission, slippage, latency, size, stop loss, take profit, or account currency. Its `net_profit_status` remains `NOT_ASSESSED`, `probability_of_profit` remains null, and `calibration_eligible` is false.

Do not feed this directional label into the profit-probability calibration evaluator. A separate financial outcome model must first define executable bid/ask entry and exit, transaction costs, invalidation, and conservative intrabar ambiguity handling, then validate those labels out of sample.

## Current integration boundary

This is a pure resolver and testable foundation. It is not yet connected to live provider candle ingestion, signal audit persistence, or a production outcome worker. Local SQLite remains single-host development storage. No orders are sent and no real execution is enabled.