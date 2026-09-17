# Stage 7 — Evidence Register

This register is a factual audit ledger for the current Stage 7 review. It does **not** authorize REAL execution and does not turn an assertion into evidence.

## Audit target

- Stage 7 head: `c3ad02499c99aabb76a15cd3c6261a01dace19a7`
- Stage 7 base: `585fb5684cf4f05b911c80463930278b4b64bcdf` (Stage 6 head)
- Current Stage 7 PR: #252
- The diagnostic CI rerun on the preceding merge tree (workflow run #1726, attempt 2) executed the full suite and reported `1651 passed, 1 failed, 2 subtests passed`; the sole failure was the new execution-surface guard, which correctly exposed three intentional low-level calls in `execution/demo_broker_port.py` and `execution/demo_risk_dispatch_guard.py` that had not yet been included in its audited-boundary allowlist.
- The guard was then tightened by explicitly classifying those two files as audited DEMO execution boundaries; the workflow was restored to the original full validation pipeline. A fresh CI execution for the current head is still required before `ci_green` is considered current.

## Verified evidence already located

| Gate | Evidence | Source | Status |
|---|---|---|---|
| `stage2_green` | CI run #1684 on Stage 2 consolidated HEAD `02f20b346d39fe7b03a91d7506a6f2aa669d327d` | GitHub Actions / commit | VERIFIED |
| `stage4_green` | CI run #1712 on Stage 4 HEAD `f677c5f347f9e9522f950909b075a305ca26cce7` | GitHub Actions / commit | VERIFIED, subject to descendant-contract review |
| `stage5_green` | PR #246 merged; Stage 5 HEAD `e269cf80b4bcbf64ec5e8f855c48abd979fd4752` and merge commit `f677c5f347f9e9522f950909b075a305ca26cce7` | Git history / PR | VERIFIED |
| `stage6_green` | PR #251 merged; Stage 6 HEAD `585fb5684cf4f05b911c80463930278b4b64bcdf` and merge commit `297514933163f8ebfbc9801373f7d896eabfa6b8` | Git history / PR | VERIFIED |

## Execution-surface finding

The current structural scan intentionally treats these as audited boundaries rather than unexplained side doors:

- `execution/adapter_gateway.py` — broker adapter gateway boundary;
- `execution/gateway.py` — execution gateway boundary;
- `execution/real_gateway.py` — REAL dispatch boundary;
- `execution/p125_sandbox_validation.py` — DEMO sandbox validation boundary;
- `execution/demo_broker_port.py` — DEMO broker port with a module-private capability required for adapter dispatch;
- `execution/demo_risk_dispatch_guard.py` — DEMO risk gate that forwards only after authoritative risk fingerprint validation.

This classification is structural evidence about where low-level calls exist; it is not, by itself, proof that every boundary is behaviorally safe. Dedicated tests and current CI remain required.

## Explicitly unresolved / requiring gate-specific proof

The following must not be represented as green merely because related code or documentation exists:

- `stage3_green`: no CI run directly attached to Stage 3 HEAD was found; descendant coverage must be proven gate-by-gate or this remains pending.
- `side_doors_scanned`: current-tree scan is now enumerated and the intentional boundaries are identified, but a passing current CI execution is still required before closure.
- `threat_model_reviewed`: current review artifact and scope must be identified.
- `secrets_reviewed`: production configuration/secrets review evidence must be identified without exposing secret values.
- `rollback_tested`: an actual rollback/recovery execution artifact is required; documentation alone is insufficient.
- `reconciliation_tested`: current executable reconciliation evidence must be linked.
- `incident_response_tested`: current incident/kill-switch exercise evidence must be linked.
- `demo_real_separation_tested`: end-to-end current evidence across code/config/API/UI must be linked.
- `legacy_compatibility_tested`: current compatibility evidence must be linked.
- `ci_green`: current head has not yet completed a successful full CI validation.

## Evidence inheritance rule

A descendant CI run may serve as evidence for an ancestor gate only when all of the following are demonstrable:

1. the descendant commit contains the ancestor commit in its history;
2. the cited CI execution ran the relevant contract/tests;
3. no later change invalidated the relevant contract;
4. the evidence reference identifies both the ancestor scope and the descendant execution;
5. the claim is limited to what that execution actually proves.

A merged PR, a PR number, a documentation statement, or a non-executed configuration value is not itself proof of a behavioral gate.

## REAL safety invariant

This register never enables REAL. The Stage 7 readiness assessment remains governance-only, and REAL authorization must remain a separate explicit control.

## Closure rule

Do not replace `PENDING`/`UNRESOLVED` entries with `VERIFIED` without a concrete, inspectable evidence reference. This file is intentionally allowed to remain incomplete while the audit is still running.
