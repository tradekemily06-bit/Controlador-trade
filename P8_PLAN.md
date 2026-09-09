# P8 — Unified Trading Orchestration

P8 connects the validated market-data foundation to the existing analysis and decision core through one broker-agnostic orchestration boundary.

Scope:
- market data request/feed;
- strategy analysis and score;
- signal quality evaluation;
- DecisionEngine evaluation;
- immutable DecisionSnapshot for auditability;
- no order execution inside the orchestrator;
- explicit fail-closed behavior when operational state or market context is unavailable.

Execution remains isolated behind ExecutionGateway and REAL remains blocked.
