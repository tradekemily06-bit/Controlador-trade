# Stage 7 — Evidence Register

This register is a factual audit ledger for the current Stage 7 review. It does **not** authorize REAL execution and does not turn an assertion into evidence.

## Audit target

- Stage 7 head: `ea3dfa4ed5579598d818909871a58a567d3453d1`
- Stage 7 base: `585fb5684cf4f05b911c80463930278b4b64bcdf` (Stage 6 head)
- Current Stage 7 PR: #252
- Current Stage 7 CI: workflow run #1720, completed successfully against the exact Stage 7 head.

## Verified evidence already located

| Gate | Evidence | Source | Status |
|---|---|---|---|
| `stage2_green` | CI run #1684 on Stage 2 consolidated HEAD `02f20b346d39fe7b03a91d7506a6f2aa669d327d` | GitHub Actions / commit | VERIFIED |
| `stage4_green` | CI run #1712 on Stage 4 HEAD `f677c5f347f9e9522f950909b075a305ca26cce7` | GitHub Actions / commit | VERIFIED, subject to descendant-contract review |
| `stage5_green` | PR #246 merged; Stage 5 HEAD `e269cf80b4bcbf64ec5e8f855c48abd979fd4752` and merge commit `f677c5f347f9e9522f950909b075a305ca26cce7` | Git history / PR | VERIFIED |
| `stage6_green` | PR #251 merged; Stage 6 HEAD `585fb5684cf4f05b911c80463930278b4b64bcdf` and merge commit `297514933163f8ebfbc9801373f7d896eabfa6b8` | Git history / PR | VERIFIED |
| `ci_green` | CI run #1720 completed SUCCESS against exact Stage 7 HEAD `ea3dfa4ed5579598d818909871a58a567d3453d1` | GitHub Actions | VERIFIED |

## Explicitly unresolved / requiring gate-specific proof

The following must not be represented as green merely because related code or documentation exists:

- `stage3_green`: no CI run directly attached to Stage 3 HEAD was found; descendant coverage must be proven gate-by-gate or this remains pending.
- `side_doors_scanned`: current-tree scan must identify the complete execution surface and its result.
- `threat_model_reviewed`: current review artifact and scope must be identified.
- `secrets_reviewed`: production configuration/secrets review evidence must be identified without exposing secret values.
- `rollback_tested`: an actual rollback/recovery execution artifact is required; documentation alone is insufficient.
- `reconciliation_tested`: current executable reconciliation evidence must be linked.
- `incident_response_tested`: current incident/kill-switch exercise evidence must be linked.
- `demo_real_separation_tested`: end-to-end current evidence across code/config/API/UI must be linked.
- `legacy_compatibility_tested`: current compatibility evidence must be linked.

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
