# Stage 2 — Final Security Gate Matrix

Status: **validation in progress**. This document is a gate record, not a release approval.

## Verified controls

- Global operational barrier is fail-closed and checked again inside the REAL dispatch lock.
- DEMO operational runtime owns the durable ledger, lifecycle, safety state, incident manager and dispatch lock.
- REAL dispatch through `RealExecutionGateway` requires the execution ledger, authoritative identity, safety revalidation and the broker gateway.
- Broker adapter identity is explicit and checked against authorization and admission before dispatch and against the adapter result after dispatch.
- Authorization, admission and request are bound by request_id, broker_id and symbol; authorization/admission adapter_id must equal the registry-resolved adapter identity.
- REAL ledger transitions are terminally protected: terminal states cannot be mutated or replayed, and uncertain operations remain UNKNOWN until explicit reconciliation.
- REAL reconciliation requires persisted broker/symbol identity and an external evidence authority; evidence identity/source are persisted and verified.
- Ledger reconciliation fails closed when evidence_id/evidence_source are absent, and regression coverage proves UNKNOWN/RESERVED cannot be reconciled without evidence.
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
- Executable AST scanning checks production execution surfaces for direct active REAL authorization/admission constructors and the intended issuer boundary.
- Issuer negative coverage checks direct construction, inactive/forged admission attempts, audit failures and safety failures.
- CI concurrency cancels superseded branch runs and the CI job timeout is bounded.
- The application startup path has regression coverage for explicit PORT selection in addition to the production WSGI container path.
- Multiprocess coverage proves one-winner request reservation, reconciliation/dispatch races, conflicting transitions, abrupt lock-holder termination and interrupted temp-file recovery.
- The public `BrokerAdapterGateway.execute(...)` compatibility surface is now non-dispatching for REAL; executable REAL dispatch requires the private gateway capability held by `RealExecutionGateway`.
- The REAL gateway invokes the adapter gateway only through `execute_from_real_gateway(...)` with the exact private capability, preserving the authoritative dispatch chain.
- Ledger persistence fsyncs the temporary file before atomic replacement and now fsyncs the parent directory after `os.replace`, closing the previously documented rename-to-directory durability gap on supported POSIX filesystems.

## Remaining Stage 2 gates

### 1. REAL broker authority / adapter API — 🟡 IMPLEMENTED, CONSOLIDATED VALIDATION REQUIRED

The deep authority audit found a real alternate execution route: `BrokerAdapterGateway.execute(...)` was callable directly and could resolve an executable adapter and dispatch a REAL request without entering `RealExecutionGateway`, without reserving the ExecutionLedger request_id and without the REAL global/admission barriers.

The authority boundary has now been hardened: the public `execute(...)` surface no longer dispatches, while the executable method requires the private REAL gateway capability and is called by `RealExecutionGateway` only after its validation, ledger reservation and dispatch-lock barriers. This is the implementation fix; final closure still requires consolidated adversarial coverage proving the direct route is blocked and the legitimate route remains executable under the complete Stage 2 harness.

### 2. REAL privilege origin / reconstruction — 🟡 IMPLEMENTED, EVIDENCE STILL OPEN

The authoritative issuer and private active-object issuance boundary are implemented. The proof is immutable and carries the complete privileged identity; active/admitted state requires that proof to remain valid. Identity rebinding and pickle-style restart reconstruction therefore fail closed.

Required evidence before Stage 2 closure:

- consolidated tests pass for direct construction, legacy reconstruction, identity rebinding and restart/reconstruction;
- no remaining legacy constructor, deserialization, compatibility helper or factory can create an active REAL privilege outside the issuer;
- full CI validates the consolidated tree after the broker-authority fix.

### 3. DecisionSnapshot identity/freshness — 🟢 IMPLEMENTED, CONSOLIDATED VALIDATION REQUIRED

The REAL gateway rejects a missing/mismatched snapshot symbol and rejects missing, future or expired snapshot timestamps using the mandatory REAL freshness policy. The live orchestrator supplies the actual decision creation timestamp.

### 4. Execution ledger reconciliation evidence — 🟢 IMPLEMENTED AND TESTED

The ledger reconciliation contract requires explicit external evidence identity and source. Missing evidence is rejected, and regression coverage locks the behavior. This closes the previously identified permissive reconciliation path at the ledger boundary; broader authority-route closure is still required.

### 5. Configuration / environment side doors — 🟡 PARTIALLY VERIFIED

DEMO provider configuration rejects known REAL provider aliases, and factory composition tests cover the intended production construction boundaries. The remaining audit must cover every production configuration/factory surface, including app/core integration paths, and prove that configuration cannot select an execution route outside the authoritative gateway. Current app configuration selects DEMO/paper providers only; environment variables do not directly select a REAL adapter gateway.

### 6. Identity mutation / cross-context reuse — 🟡 PARTIALLY VERIFIED

REAL authorization/admission objects are identity-bound and immutable, and request_id/external_id replay protections exist in the ledger and REAL gateway. The remaining closure work is to prove the same invariant across every composition and restart path, not merely the ledger API.

### 7. Cross-process authority / recovery matrix — 🟢 STRONG COVERAGE, FINAL CLOSURE PENDING

Multiprocess tests cover reservation races, reconciliation races, conflicting transitions, abrupt lock-holder termination, crash-after-external-acceptance, restart without replay and interrupted temp-file recovery. Final closure still depends on the complete authority graph, including configuration/reconstruction routes and the final broker boundary regression.

### 8. Durability boundary — 🟡 IMPLEMENTED, VALIDATION REQUIRED

Ledger writes fsync the temporary file, atomically replace the target, and then fsync the parent directory. This establishes the intended file-plus-directory persistence sequence for supported POSIX filesystems. Final Stage 2 closure still requires CI/adversarial validation of the persistence path and explicit confirmation of the supported filesystem contract; the implementation no longer relies solely on the pre-rename file fsync.

## Current CI evidence

The current Stage 2 head is **`dd98a56ab32f2fa62434d6e64064029cb1f665db`**. CI run **#1662** completed successfully for that commit, including the full test suite, dependency security audit, Python compilation, production container build and production health smoke test.

The subsequent commits **`529ea4c3247114515cdd3a4eb5a55b7dfe059fbb`** and this matrix update are newer than that successful CI run, so the current final tree is **not yet CI-validated**. A new CI run must complete successfully on the latest head before any Stage 2 closure claim.

The branch remains validation-only and must not be merged until the remaining authority gates above are closed.

## Stage 2 closure rule

Stage 2 remains **not closed** until every OPEN/validation-pending gate has implementation evidence, adversarial coverage, and a green consolidated CI run on the final head. No REAL enablement is implied by this document.
