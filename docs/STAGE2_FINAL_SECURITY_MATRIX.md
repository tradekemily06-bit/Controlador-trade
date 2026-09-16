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
- REAL gateway now binds DecisionSnapshot.symbol to the request symbol and enforces snapshot timestamp/freshness before REAL dispatch.
- The live orchestrator now persists the decision creation timestamp into the DecisionSnapshot instead of producing a timestamp-less operational snapshot.
- Active REAL authorization can only be constructed through the private issuer boundary; direct construction of an active authorization fails closed.
- Active REAL admission can only be constructed through the private issuer boundary; the legacy public admission path can only produce BLOCKED state and cannot manufacture an admitted privilege.
- RealPrivilegeIssuer derives adapter identity from the authoritative BrokerAdapterGateway and admission identity from the already-issued authorization.
- Issuer negative coverage now checks direct active authorization/admission construction, inactive/forged admission attempts, audit failures and safety failures.
- CI concurrency was changed to cancel superseded branch runs and a 30-minute job timeout was added.

## Remaining Stage 2 gates

### 1. REAL privilege origin / reconstruction — 🟡 IMPLEMENTED, EVIDENCE STILL OPEN

The authoritative issuer and private active-object issuance boundary are now present. The remaining proof is not implementation but complete coverage of every legacy/reconstruction path and the full consolidated suite.

Required evidence before Stage 2 closure:

- no legacy constructor, deserialization, compatibility helper or factory can create an active REAL privilege outside the issuer;
- restart/reconstruction preserves the issuer invariant;
- negative tests prove direct construction, legacy reconstruction and mismatched issuer context cannot reach REAL dispatch;
- full CI validates the consolidated tree.

### 2. DecisionSnapshot identity/freshness — 🟢 IMPLEMENTED, TEST SUITE VALIDATION PENDING

The REAL gateway now rejects a missing/mismatched snapshot symbol and rejects missing, future or expired snapshot timestamps using the mandatory REAL freshness policy. The live orchestrator supplies the actual decision creation timestamp.

The gate remains pending only until the consolidated CI/test suite proves these controls together with the rest of Stage 2.

### 3. CI consolidated validation — 🔴 OPEN / INFRASTRUCTURE QUEUE

The newest validation run for the current branch is the authoritative run to watch. A queued run is not a failure and is not evidence of a green build. Stage 2 cannot close until the current consolidated tree actually starts and completes successfully.

## Stage 2 closure rule

Stage 2 remains **not closed** until all OPEN/validation-pending gates above have implementation evidence, legacy/reconstruction coverage, and the consolidated CI run is green. No REAL enablement is implied by this document.
