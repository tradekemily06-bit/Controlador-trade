# P10 — Controlled Trading Runtime

P10 adds a bounded runtime layer over the validated P8/P9 flow.

Scope:
- repeat the existing orchestration in explicit cycles;
- create an execution plan only when the existing decision is EXECUTAR;
- route execution only through ExecutionCoordinator/ExecutionGateway;
- stop the runtime safely after an execution rejection/block;
- deterministic request IDs by cycle when no factory is supplied;
- keep the runtime broker-agnostic and DEMO-only through the existing gateway contract;
- no new trading strategy, broker calls, or REAL execution.

Validation criteria:
- invalid cycle limits are rejected;
- non-executable decisions never create or execute a plan;
- executable decisions create a plan with deterministic IDs;
- rejected/blocked execution stops later cycles;
- execution remains behind the coordinator/gateway boundary;
- full test suite and project compilation pass in CI.

The runtime is intentionally bounded by `max_cycles`; continuous scheduling and external market-data polling remain separate concerns for later stages.