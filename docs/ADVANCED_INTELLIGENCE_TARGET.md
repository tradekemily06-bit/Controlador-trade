# Advanced intelligence target (research-grade, ASI-inspired)

## Product intent

The Ecossistema is intended to become a deeply integrated, continuously improving market-intelligence application. "ASI-inspired" describes the ambition and engineering direction; it is not a claim that the current or planned system is artificial superintelligence, AGI, autonomous financial authority, or infallible.

The system must preserve the six approved visible areas and the existing frontend. Intelligence is a shared internal capability, not a seventh navigation area.

## Intelligence layers

1. **Evidence ingestion** — broker candles and quotes, market structure, volume where available, economic calendar, official releases, reputable news, and other explicitly configured feeds. Every observation carries provider, source timestamp, ingestion timestamp, asset scope, and freshness state.
2. **Normalization and provenance** — canonical symbols, currencies, timeframes, event types, units, time zones, duplicate detection, source reliability metadata, and explicit missing-data records.
3. **Context graph** — relate macro events, instruments, correlated markets, sessions, volatility regimes, liquidity conditions, and prior observations. Every relationship must retain its evidence and temporal validity.
4. **Independent analysis** — technical, macroeconomic, event/news, cross-asset, temporal, liquidity and risk analyses run as separate evidence-producing components before synthesis.
5. **Adversarial synthesis** — produce supporting evidence, counterevidence, conflicts, missing inputs, alternative explanations and a reasoned abstention when evidence is insufficient. Do not average incompatible signals into false certainty.
6. **Forecast evaluation** — track forecasts against later observed outcomes; use out-of-sample data, context isolation, calibration diagnostics and drift detection. Never display a probability as calibrated until it passes the documented validation policy.
7. **Persistent learning and audit** — store versioned decisions, source provenance, model/rule versions, user annotations, realized outcomes and correction history with tenant isolation.
8. **Human-facing explanation and alerts** — explain what changed, why it matters, affected instruments, source links, timestamp, confidence limitations and what would invalidate the assessment. Alerts must be deduplicated and severity-gated.

## Required behavior

- Prefer multiple independent sources; distinguish official primary sources from media reporting and commentary.
- Distinguish confirmed facts, attributed claims, estimates, forecasts, rumors and unverified reports.
- Never infer market direction from a headline keyword. The initial news classifier is triage only: it labels possible event categories/assets and does not calculate sentiment, direction or impact probability.
- Do not silently fill missing data, stale candles, missing calendar fields or provider outages. Mark them and reduce the scope of conclusions.
- Resolve conflicting providers explicitly; show disagreement rather than choosing the most convenient value.
- Keep all broker adapters read-only for analysis. Order execution remains in its separate authorization, safety, admission and manual-confirmation boundary.
- Preserve REAL authorization already given by the owner. Never ask the owner to repeat it. REAL dispatch must still be gated by concrete deployment prerequisites and a fresh human confirmation for each order.
- No FOMO feature, urgency manipulation, fabricated countdowns, or pressure language.

## Measurable acceptance gates

- **Source integrity:** every market/news/calendar fact has source identity and timestamps; invalid, duplicate, stale or untrusted records are rejected or visibly quarantined.
- **News coverage:** tests cover major central-bank, inflation, employment, GDP, geopolitical, energy, regulatory and corporate events; unknown headlines remain unclassified instead of being forced into a category.
- **Cross-source reasoning:** conflicting observations produce an explicit conflict record and do not create an unsupported directional call.
- **Forecast quality:** Brier score, log loss, reliability bins, sample count, context and model version are retained; no calibration claim from in-sample or simulated outcomes.
- **Temporal integrity:** each timeframe cycle uses the provider's confirmed closed candle and exposes latency, gaps, reconnects and stale status.
- **Learning quality:** every model/rule change is versioned, evaluated out of sample and reversible; no automatic promotion based only on a recent winning streak.
- **Safety:** analysis, memory, learning and notifications cannot grant order authority; REAL dispatch is separately gated and manually confirmed.
- **Reliability:** workers survive process restarts through durable queues/state; push delivery is verified on a real device with the app closed before being called operational.
- **Honesty:** readiness labels distinguish implemented, configured, connected, live-tested and production-validated states.

## Current implementation evidence and gaps

- A shared intelligence coordinator and senior context pipeline exist; they are not evidence of AGI/ASI.
- Probability calibration diagnostics exist and intentionally withhold an approved probability.
- RSS/Atom ingestion exists and can be configured through `CONTROLADOR_NEWS_FEEDS`; it is not yet proof of continuous production news coverage.
- The new headline triage module is deterministic and deliberately non-directional. It is not NLP sentiment, causal analysis, a calendar feed, or a full article understanding system.
- Economic-calendar ingestion, multi-source corroboration, event-to-market causal evaluation, a persistent cross-market context graph, drift monitoring, and end-to-end UI wiring remain explicit implementation work.
- Production hosting, provider credentials, live broker handshakes, durable push delivery and real-device verification remain external deployment gates.

## Delivery discipline

Do not label a feature "complete" based on a class existing or a unit test passing alone. Completion requires code, tests, provider evidence, API exposure, frontend wiring where applicable, operational telemetry and documented limitations.
