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
- Ledger reconciliation now fails closed when evidence_id/evidence_source are absent, and regression coverage proves UNKNOWN/RESERVED cannot be reconciled without evidence.
- External order observations require request, source, broker and symbol metadata and fail closed when those bindings are missing or inconsistent.
- Demo broker direct-dispatch side doors are blocked; the gateway-bound capability is required for DEMO broker execution.
- Production factory composition is guarded against raw MT5 adapter injection and unauthorized REAL gateway construction.
- Decision freshness exists as a fail-closed policy and is bound by the consolidated DEMO operational runtime.
- REAL gateway binds DecisionSnapshot.symbol to the request symbol and enforces snapshot timestamp/freshness before REAL dispatch.
- The live orchestrator persists the decision creation timestamp into the DecisionSnapshot instead of producing a timestamp-less operational snapshot.
- Active REAL authorization can only be constructed through the private issuer boundary; direct construction of an active authorization fails closed.
- Active REAL admission can only be constructed through the private issuer boundary; the legacy public admission path can only produce BLOCKED state and cannot manufacture an admitted privilege.
- RealPrivilegeIssuer derives authorization identity from the trusted ExecutionRequest and adapter identity from the authoritative BrokerAdapterGateway; admission identity is derived from the already-issued authorization.
- REAL authorization and admission provenance proofs are immutable and identity-bound, so dataclasses.replace or field rebinding cannot preserve an active/admitted privilege.
- Legacy/pickle-style reconstruction fails closed when the private issuance proof is absent or no longer valid.
- Executable AST scanning checks production surfaces for direct active REAL authorization/admission constructors and the intended issuer boundary.
- Issuer negative coverage checks direct construction, inactive/forged admission attempts, audit failures and safety failures.
- CI concurrency was changed to cancel superseded branch runs and a 30-minute job timeout was added.
- The application startup path now has regression coverage for explicit PORT selection in addition to the production WSGI container path.

## Remaining Stage 2 gates

### 1. REAL privilege origin / reconstruction — 🟡 IMPLEMENTED, EVIDENCE STILL OPEN

The authoritative issuer and private active-object issuance boundary are implemented. The deep reconstruction review identified a second-order provenance issue: a singleton issuer token by itself was not enough to bind the privilege to its identity. The proof is now immutable and carries the complete privileged identity; `active`/`admitted` require that proof to remain valid. This makes identity rebinding fail closed and makes restart-style reconstruction fail closed when the proof cannot be re-established.

Required evidence before Stage 2 closure:

- consolidated tests pass for direct construction, legacy reconstruction, identity rebinding and restart/reconstruction;
- no remaining legacy constructor, deserialization, compatibility helper or factory can create an active REAL privilege outside the issuer;
- full CI validates the consolidated tree.

### 2. DecisionSnapshot identity/freshness — 🟢 IMPLEMENTED, TEST SUITE VALIDATION PENDING

The REAL gateway rejects a missing/mismatched snapshot symbol and rejects missing, future or expired snapshot timestamps using the mandatory REAL freshness policy. The live orchestrator supplies the actual decision creation timestamp.

The gate remains pending only until the consolidated CI/test suite proves these controls together with the rest of Stage 2.

### 3. CI consolidated validation — 🟢 LATEST RUN GREEN

The latest consolidated validation run for the current Stage 2 head is **35148578751** on commit **4ff9731796ee9b322675f236754db51bfb768a1d**. It completed successfully. This run is evidence for the current tree, but CI success alone does not close the remaining deep-audit gates.

### 4. Execution ledger reconciliation evidence — 🟢 IMPLEMENTED AND TESTED

The ledger reconciliation contract now requires explicit external evidence identity and source. Missing evidence is rejected, and regression coverage locks the behavior. This closes the previously identified permissive reconciliation path at the ledger boundary; the remaining Stage 2 closure still requires the broader reconstruction, route, concurrency and identity audit evidence.

## Stage 2 closure rule

Stage 2 remains **not closed** until all OPEN/validation-pending gates above have implementation evidence, legacy/reconstruction coverage, and the consolidated CI run is green. No REAL enablement is implied by this document.
