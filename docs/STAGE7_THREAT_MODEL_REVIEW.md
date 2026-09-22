# Stage 7 — Threat Model Review

## Purpose

This document records a code-level threat-model review for the Stage 7 audit target. It is evidence of a structured review, not a claim that external infrastructure, broker accounts, deployment controls, or production secrets have been independently inspected.

The review is deliberately fail-closed: a missing control is treated as a release blocker rather than an assumption.

## Assets that require protection

- REAL execution authority and the authenticated issuer that can create it.
- Broker and adapter identity bound to each execution request.
- Request, decision, risk, ledger, lifecycle, and reconciliation identities.
- Execution state, especially `RESERVED` and `UNKNOWN` states.
- Kill switch, incident, maintenance, and global operational barriers.
- Tenant/user scope and product-layer state.
- Secrets, credentials, tokens, and broker connection material.
- Audit evidence needed to reconstruct an operation after failure.

## Trust boundaries

1. Decision/analysis layer → risk/admission layer.
2. Admission/authorization → execution gateway.
3. Execution gateway → broker adapter gateway.
4. Broker adapter gateway → concrete broker adapter.
5. Dispatch → ledger/lifecycle persistence.
6. External broker result → reconciliation authority.
7. Product/UI/SaaS layer → core operational authority.
8. Configuration/secrets → runtime infrastructure.

The product/UI layer is not trusted to create REAL authority. The broker adapter is not trusted to define its own identity or safety state. Observability is not trusted to authorize execution.

## Threat catalogue and required controls

| Threat | Control required | Current code-level evidence | Residual scope |
|---|---|---|---|
| UI/API creates REAL privilege | REAL authorization must originate from an internal authoritative path | `RealExecutionAuthorization` + Stage 6 boundary tests | Deployment/API integration review still required |
| DEMO path reaches REAL adapter | Separate DEMO gateway and broker capability boundaries | DEMO-only `ExecutionGateway`; private broker capability; Stage 7 execution-surface guard | End-to-end deployed UI/API test pending |
| Adapter substitution | Bind authorization/admission/request to resolved adapter identity | `RealExecutionGateway._validate_context_binding` | Live provider exercise pending |
| Replay/duplicate request | Durable ledger + request identity + locks | execution ledger and dispatch-lock paths | Production storage exercise pending |
| UNKNOWN is replayed automatically | UNKNOWN/RESERVED require explicit reconciliation | REAL gateway and recovery tests | External broker reconciliation exercise pending |
| Risk changes after decision | Re-read authoritative risk state immediately before dispatch | REAL and DEMO gateway revalidation | Live environment exercise pending |
| Safety changes after admission | Re-read authoritative REAL safety immediately before dispatch | REAL gateway safety revalidation | Live environment exercise pending |
| Global incident/maintenance/kill switch bypass | Final fail-closed barrier immediately before dispatch | `ExecutionGateway._final_safety_barrier`; global barrier in REAL path | Operational exercise evidence pending |
| Low-level side door | Detect low-level `.execute()` outside audited boundaries | `tests/test_stage7_execution_surface.py` | Historical deployment binaries not in repository are out of scope |
| Persistence failure after broker acceptance | Convert state to UNKNOWN and require reconciliation | REAL gateway ledger handling | Broker-side confirmation exercise pending |
| Malformed/ambiguous broker result | Treat as UNKNOWN | adapter gateway + REAL gateway | Live provider exercise pending |
| Secret leakage in logs/errors | Redact and avoid returning secret values | Stage 5 redaction controls | External log sink review pending |
| Tenant cross-access | Explicit tenant/user scoping | Stage 6 SaaS boundary tests | Production data-plane review pending |
| Learning/lab influences operation authority | Learning boundary must remain non-authoritative | Stage 6 learning boundary tests | Future product integration review pending |

## Abuse paths reviewed

### A. Product → execution

A product-layer request must not be able to manufacture REAL authorization. Execution authority remains in core execution boundaries. A product failure must fail closed rather than provide a fallback executor.

### B. DEMO → REAL

The ordinary execution gateway validates DEMO mode. The broker registry keeps executable adapters behind a module-private capability, while the REAL path has a separate gateway and explicit authorization/admission requirements.

### C. Timeout/exception → duplicate order

A broker exception or uncertain result is represented as UNKNOWN and persisted before any future reconciliation. RESERVED/UNKNOWN requests are not replayed automatically.

### D. Risk/safety race → unsafe dispatch

Final risk and safety checks occur under the dispatch lock immediately before the adapter call. A changed identity blocks the dispatch and requires a new decision/admission cycle.

### E. Incident/kill-switch race → unsafe dispatch

The operational barriers are evaluated immediately before dispatch. Failure to obtain a valid barrier state is fail-closed.

## Security invariants that must remain true

1. No UI/API/configuration path creates REAL authority.
2. REAL dispatch requires active explicit authorization and matching admission.
3. `request_id`, broker, symbol, and adapter identity must agree across the dispatch context.
4. `RESERVED` and `UNKNOWN` are terminally unsafe for replay until explicit reconciliation.
5. Ambiguous broker outcomes are never silently treated as accepted.
6. A missing, invalid, or unavailable safety barrier blocks dispatch.
7. Observability and learning features never become authorization sources.
8. This review never enables REAL.

## Review limitations

This is a repository/code-level threat-model review. It does **not** prove:

- broker-provider production behavior;
- cloud/IAM/network configuration;
- GitHub organization secrets or external secret stores;
- production database isolation;
- real rollback execution;
- live incident-response exercise;
- live external-order reconciliation.

Those items remain separate evidence gates and must not be inferred from this document.

## Review conclusion

The repository contains explicit control points for the major execution, replay, identity, safety, and product-boundary threats listed above. The remaining limitations are recorded as evidence gaps rather than being silently promoted to verified production claims.
