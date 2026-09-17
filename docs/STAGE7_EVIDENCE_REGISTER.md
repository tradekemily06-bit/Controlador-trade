# Stage 7 — Evidence Register

This register is a factual audit ledger for the current Stage 7 review. It does **not** authorize REAL execution and does not turn an assertion into evidence.

## Audit target

- Current Stage 7 PR: #252.
- Stage 7 base: `585fb5684cf4f05b911c80463930278b4b64bcdf` (Stage 6 head).
- Current audit target: `2eb4b1996fab3440be95e80fe03c584d99cff00b`.
- CI workflow run #1796 and CodeQL run #9 completed successfully on `2eb4b1996fab3440be95e80fe03c584d99cff00b` before this register update.
- This register update creates a new audit-target commit; therefore the resulting HEAD requires a fresh CI execution before `ci_green` is considered current for the final audit target.

## Verified evidence already located

| Gate | Evidence | Source | Status |
|---|---|---|---|
| `stage2_green` | CI run #1684 on Stage 2 consolidated HEAD `02f20b346d39fe7b03a91d7506a6f2aa669d327d` | GitHub Actions / commit | VERIFIED |
| `stage4_green` | CI run #1712 on Stage 4 HEAD `f677c5f347f9e9522f950909b075a305ca26cce7` | GitHub Actions / commit | VERIFIED, subject to descendant-contract review |
| `stage5_green` | PR #246 merged; Stage 5 HEAD `e269cf80b4bcbf64ec5e8f855c48abd979fd4752` and merge commit `f677c5f347f9e9522f950909b075a305ca26cce7` | Git history / PR | VERIFIED |
| `stage6_green` | PR #251 merged; Stage 6 HEAD `585fb5684cf4f05b911c80463930278b4b64bcdf` and merge commit `297514933163f8ebfbc9801373f7d896eabfa6b8` | Git history / PR | VERIFIED |
| `side_doors_scanned` | Structural execution-surface guard and REAL authorization-factory consumer guard passed in CI #1783 on `cb2ccec2f735b62c12362a4123eb7a3a3da9b6be`; the low-level REAL authorization factory is now capability-gated and structurally restricted to the dedicated issuer | GitHub Actions / tests | VERIFIED for that target; must be revalidated on final audit target |
| `ci_green` | CI #1783 on `cb2ccec2f735b62c12362a4123eb7a3a3da9b6be`; full suite, dependency audit, compile, production container build, and smoke health test all succeeded | GitHub Actions | VERIFIED for that target; pending final register commit |
| `secrets_reviewed` | GitHub Secret Scanning enabled; current open-alert query returned zero alerts with secret literals hidden; push protection enabled | GitHub security settings / Secret Scanning | VERIFIED for repository-detected provider secrets; external deployment secrets remain outside repository evidence scope |
| `repository_governance` | `main` branch protection verified: required `test` status check, strict up-to-date requirement, enforced for admins, no force-push/deletion, linear history, conversation resolution | GitHub branch protection | VERIFIED |

## Stage 3 descendant evidence

Stage 3 consolidated HEAD `31c18b5ce51623c38205a27fb6d0c05481113b4b` is an ancestor of the Stage 7 audit target: the comparison reports 63 commits ahead and zero commits behind. The current full CI pipeline on the descendant therefore provides regression evidence for contracts still present in the descendant tree, but it does not automatically prove every historical Stage 3 requirement.

- `stage3_green`: descendant contract mapping is now concrete and current CI #1796 executes the relevant descendant tests. Gate A composition/topology is covered by `tests/test_stage3_production_topology.py` and `tests/test_stage3_production_state_authority.py`; Gate B identity by `tests/test_stage3_demo_market_identity.py`; Gate C controlled DEMO execution by `tests/test_stage3_mt5_demo_readiness.py` plus current Stage 7 execution/reconciliation suites; Gate D failure/restart/reconciliation by `tests/test_stage4_recovery_matrix.py`, `tests/test_stage7_resilience_e2e.py`, `tests/test_stage7_ledger_lifecycle_crash_windows.py`, and `tests/test_stage7_reconciliation_race.py`; Gate E observability/identity is covered by the descendant Stage 5 observability contract suite. The current CI run is therefore evidence for the mapped contracts, not merely ancestry.

## Execution-surface finding

The current structural scan intentionally treats these as audited boundaries rather than unexplained side doors:

- `execution/adapter_gateway.py` — broker adapter gateway boundary;
- `execution/gateway.py` — execution gateway boundary;
- `execution/real_gateway.py` — REAL dispatch boundary;
- `execution/p125_sandbox_validation.py` — DEMO sandbox validation boundary;
- `execution/demo_broker_port.py` — DEMO broker port with a module-private capability required for adapter dispatch;
- `execution/demo_risk_dispatch_guard.py` — DEMO risk gate that forwards only after authoritative risk fingerprint validation.

The REAL authorization surface now has an additional low-level capability check: direct construction with identical public fields remains inactive, while the active factory requires an exact in-process issuer capability. Structural tests also reject new production consumers of that factory outside the dedicated issuer module.

This classification is structural evidence about where low-level calls exist; it is not, by itself, proof that every boundary is behaviorally safe. Dedicated tests and current CI remain required.

## Explicitly unresolved / requiring gate-specific proof

The following must not be represented as green merely because related code or documentation exists:

- `threat_model_reviewed`: current review artifact and scope must be identified.
- `rollback_tested`: an actual rollback/recovery execution artifact is required; documentation alone is insufficient.
- `demo_real_separation_tested`: end-to-end current evidence across code/config/API/UI must be linked.
- `ci_green`: a fresh run is required after this register update commit.

### Newly exercised current evidence

- `reconciliation_tested`: current cross-process reconciliation race tests and end-to-end broker-evidence reconciliation are present and passed in CI #1796.
- `incident_response_tested`: current incident persistence/restart/recovery exercises are present and passed in CI #1796.
- `legacy_compatibility_tested`: current legacy REAL rejection, legacy snapshot boundary, and fabricated-authority provenance tests are present and passed in CI #1796.
- `demo_real_separation_tested`: current Stage 3 DEMO adapter tests, legacy gateway REAL rejection, REAL gateway provenance/barrier tests, and execution-surface guards passed in CI #1796; final API/UI/deployment evidence is still outside this code-only proof.

## Evidence inheritance rule

A descendant CI run may serve as evidence for an ancestor gate only when all of the following are demonstrable:

1. the descendant commit contains the ancestor commit in its history;
2. the cited CI execution ran the relevant contract/tests;
3. no later change invalidated the relevant contract;
4. the evidence reference identifies both the ancestor scope and the descendant execution;
5. the claim is limited to what that execution actually proves.

A merged PR, a PR number, a documentation statement, or a non-executed configuration value is not itself proof of a behavioral gate.

## REAL safety invariant

This register never enables REAL. The Stage 7 readiness assessment remains governance-only, and REAL authorization must remain a separate explicit control. The current issuer provenance is an in-process capability mechanism, not cryptographic human/operator authentication.

## Closure rule

Do not replace `PENDING`/`UNRESOLVED` entries with `VERIFIED` without a concrete, inspectable evidence reference. This file is intentionally allowed to remain incomplete while the audit is still running.
