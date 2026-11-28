# Recommendation Intelligence — Integration Audit

Date: 2026-11-28
Branch: `fix/six-visible-areas-memory-capability`

## Product boundary

Recommendation intelligence is an internal, cross-cutting capability. It is not a visible module and does not add a seventh area. The six approved areas and Lovable presentation remain unchanged. The intelligence layer may inform Analysis, Study, Command Cabin and relevant notifications, but it cannot submit orders or move money. REAL remains disabled.

## What exists in the repository

### 1. Versioned technical signal pipeline

- `analysis/pipeline.py` exposes the registered `StrategyPipeline`.
- `analysis/versioned_strategy_replay.py` registers `technical-pipeline-v1`.
- Replay uses a 30-candle warm-up and passes only the current candle plus its past to the strategy, avoiding future-candle look-ahead in the decision stream.
- The adapter records a selection/holdout trial through the tenant-scoped strategy trial ledger.
- It explicitly reports caller-supplied candles as not independently verified, gross-of-cost backtest limitations, `promotion_allowed=false`, `execution_authorized=false`, and `orders_submitted=false`.

### 2. Statistical robustness components

`analysis/strategy_robustness.py` contains:
- Probabilistic Sharpe Ratio (PSR).
- Deflated Sharpe Ratio (DSR), requiring the Sharpe values for all strategy trials.
- Block bootstrap confidence intervals.
- Rolling-window Sharpe stability.
- Cost stress testing, requiring at least a 2x cost scenario.
- Out-of-sample, benchmark, sample-size and trade-count gates.
- CSCV Probability of Backtest Overfitting (PBO) via `analyze_backtest_overfitting`.

The evaluator is deliberately conservative. It requires net returns, aligned benchmark and stress returns, untouched out-of-sample data, at least 60 observations, at least 30 completed trades, and complete selection-trial Sharpe inputs before meaningful robustness assessment. Even `ROBUST_REQUIRES_REVIEW` is not automatic promotion.

### 3. News intelligence

`analysis/news_event_intelligence.py` classifies feed headlines and summaries with transparent keyword rules, maps possible event categories and affected assets, and records ambiguity. It explicitly leaves sentiment, directional bias and impact probability unassessed, and flags that the full article has not been verified.

This is an evidence triage component, not yet a contextual news-to-market forecast. A headline alone must never generate a signal, probability or trading instruction.

## What is not yet integrated or proven

1. The standalone registered replay accepts caller-supplied candle payloads; it is not yet bound to immutable, authenticated provider snapshots with source, tenant/account, canonical instrument, timeframe, candle close, receipt time, checksum and freshness/gap status.
2. Replay performance is gross of spread, commission, slippage and swap; no trustworthy net return stream is currently supplied to the robustness evaluator by the standalone Estudo path.
3. The PSR/DSR/bootstrap/rolling/CSCV-PBO components are not wired end-to-end to the standalone trial ledger and Estudo workflow. The full matrix of all tried strategy variants and their aligned return streams is required; a selected strategy alone is insufficient.
4. No calibrated probability of profit is established. Signal score, rule-match confidence, PSR/DSR and win rate are different quantities and must not be displayed as interchangeable.
5. News classification is not yet full-article corroboration or a measured causal/temporal relationship with price, volume, volatility and economic-calendar events.
6. Operational outcomes are not yet durably reconciled, tenant-isolated and fed back into the Study review path. Unverified outcomes must remain excluded from learning.

## Required end-to-end recommendation contract

Every recommendation exposed to the user must carry:
- canonical instrument and timeframe;
- signal and timestamp, including candle-close status;
- source/provider provenance and freshness;
- strategy/model version and input snapshot fingerprint;
- evidence supporting and contradicting the recommendation;
- separate signal strength and calibrated probability fields (probability omitted unless calibrated);
- risk context, invalidation level and explicit reasons to wait;
- transaction-cost assumptions and net-of-cost evaluation status;
- sample size, selection/holdout separation and robustness diagnostics;
- news source, publication time, verification state, event category, affected assets and ambiguity;
- status such as `INSUFFICIENT_DATA`, `UNVERIFIED`, `FRAGILE`, `ROBUST_REQUIRES_REVIEW`; never imply approval from a raw score;
- `execution_authorized=false`.

## Completion gates

The recommendation intelligence is not complete until automated tests prove:
1. provider snapshot integrity, closed-candle handling, freshness and gap rejection;
2. no look-ahead across every registered strategy and timeframe;
3. realistic fills and net returns after spread, commission, slippage and swap;
4. complete trial accounting and selection/holdout isolation;
5. PSR, DSR, bootstrap, rolling stability and CSCV/PBO consume the same versioned return dataset and fail closed on missing inputs;
6. news corroboration, deduplication, timestamps, source trust and contradictory evidence are preserved;
7. calibrated probabilities are validated on untouched future periods before being shown;
8. recommendation explanations are reproducible from stored evidence;
9. no recommendation path can submit orders or enable REAL;
10. all capabilities are accessible through the existing six areas without UI redesign.

## Next implementation order

1. Build authenticated immutable provider snapshots and feed them into registered replay.
2. Add a cost-aware fill/return engine and persist per-period net returns with strategy-version and dataset fingerprints.
3. Wire the full trial matrix and robustness diagnostics into Estudo; retain human review and prohibit automatic promotion.
4. Connect trusted reconciled outcomes to durable tenant-scoped operational memory.
5. Expand news/calendar corroboration and only then evaluate cross-domain market impact.
6. Add calibration and drift monitoring only after enough verified, untouched outcomes exist.

## Honest status

The repository contains meaningful signal, trial-ledger, robustness and news-classification components. It does not yet contain a proven end-to-end recommendation engine with verified live provider data, net-of-cost validation, calibrated profit probabilities and operational feedback. The current recommendation intelligence is therefore **FOUNDATION PARTIAL — NOT PRODUCTION-VALIDATED**.
