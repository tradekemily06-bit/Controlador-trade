# Stage 2 — Final Security Gate Matrix

Status: **validation in progress**. This document is a gate record, not a release approval.

## Verified controls

- Global operational barrier is fail-closed and checked again inside the REAL dispatch lock.
- DEMO operational runtime owns the durable ledger, lifecycle, safety state, incident manager and dispatch lock.
- REAL dispatch uses the broker gateway boundary; raw adapter dispatch is not an intended parallel production path.
- Broker adapter identity is explicit and checked against authorization and admission before dispatch and against the adapter result after dispatch.
- Authorization, admission and request are bound by request_id, broker_id and symbol; authorization/admission adapter_id must equal the registry-resolved adapter identity.
- REAL ledger transitions are terminally protected: terminal states cannot be mutated or replayed, and uncertain operations remain UNKNOWN until explicit reconciliation.
- REAL reconciliation requires persisted broker/symbol identity and an external evidence authority; evidence identity/source are persisted and verified.
- External order observations require request, source, broker and symbol metadata and fail closed when those bindings are missing or inconsistent.
- Demo broker direct-dispatch side doors are blocked; the gateway-bound capability is required for DEMO broker execution.
- Production factory composition is guarded against raw MT5 adapter injection and unauthorized REAL gateway construction.
- Decision freshness exists as a fail-closed policy and is bound by the consolidated DEMO operational runtime.
- CI concurrency was changed to cancel superseded branch runs and a 30-minute job timeout was added.

## Remaining Stage 2 gates

### 1. REAL privilege origin / issuance — OPEN

`RealExecutionAuthorization` and `RealAdmission` are immutable and strongly identity-bound, but their public constructors still allow callers to construct privileged-looking values directly. The final design must establish one authoritative issuance boundary and prevent a caller from manufacturing an active REAL authorization/admission outside that boundary.

Required evidence before Stage 2 closure:

- one authoritative issuer/factory for REAL authorization;
- one authoritative issuer/factory for REAL admission;
- privileged identity derived from the trusted request/authorization/registry context rather than accepted as caller-controlled identity;
- no legacy constructor, deserialization, compatibility helper or factory can create an active REAL privilege outside that issuer;
- restart/reconstruction preserves the issuer invariant;
- negative tests prove direct construction, legacy reconstruction and mismatched issuer context cannot reach REAL dispatch.

### 2. DecisionSnapshot identity — OPEN

The REAL gateway currently binds request/authorization/admission symbol identity, but the final REAL boundary must also bind `DecisionSnapshot.symbol` to the request symbol. A snapshot for one instrument must never authorize a request for another instrument, even when the request and authorization agree with each other.

The REAL boundary must also enforce the snapshot timestamp/freshness contract, not merely the DEMO operational gateway.

### 3. CI #1536 — OPEN / INFRASTRUCTURE QUEUE

Run 1536 is still queued. This is not evidence of a test failure and it is not evidence of a green build. The workflow has already been changed to prevent stale runs from accumulating, but the current queued run must actually start and complete before the final matrix can be marked green.

## Stage 2 closure rule

Stage 2 remains **not closed** until all OPEN gates above have implementation evidence and the consolidated CI run is green. No REAL enablement is implied by this document.
