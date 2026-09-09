# P9 — Controlled Execution Bridge

P9 connects an already evaluated orchestration result to the existing ExecutionGateway through an explicit execution plan.

Scope:
- derive an execution plan only from `EXECUTAR` decisions;
- preserve the existing Signal and symbol from the analysis result;
- default execution mode to DEMO;
- forward the immutable DecisionSnapshot to the existing gateway for auditability;
- keep kill-switch, duplicate protection, request validation and execution isolation inside ExecutionGateway;
- no new trading strategy and no direct broker calls.

REAL execution remains blocked by the existing gateway contract.
