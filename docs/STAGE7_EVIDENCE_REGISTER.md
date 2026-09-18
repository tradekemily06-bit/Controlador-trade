# Stage 7 — Evidence Register

This register is a factual audit ledger for the current Stage 7 review. It does **not** authorize REAL execution and does not turn an assertion into evidence.

## Audit target

- Current Stage 7 PR: #252.
- Stage 7 base: `585fb5684cf4f05b911c80463930278b4b64bcdf` (Stage 6 head).
- Current audit target: the commit created by this evidence-register refresh; a fresh CI/CodeQL/rollback execution is required for that exact commit.
- CI #1815, CodeQL #28, and rollback drill #16 passed on predecessor `3b5b8c658f50311867b509fd5716253e932f3d59`; they are predecessor evidence only until this register refresh receives fresh checks.
- Stage 7 controlled rollback drill run #1 and artifact `stage7-rollback-evidence` (artifact id `10526753950`) remain valid evidence for the older exercised commit, but are not claimed as execution evidence for this new target.
- The readiness model now rejects evidence references whose `commit_sha` differs from the declared target commit.
- This register update creates a new audit-target commit; therefore the resulting HEAD requires fresh CI/CodeQL/rollback execution before current evidence is considered final.

## Verified evidence already located

| Gate | Evidence | Source | Status |
|---|---|---|---|
| `stage2_green` | CI run #1684 on Stage 2 consolidated HEAD `02f20b346d39fe7b03a91d7506a6f2aa669d327d` | GitHub Actions / commit | VERIFIED |
| `stage3_green` | Descendant contract mapping plus current Stage 7 CI coverage | Git history / tests / CI | VERIFIED for mapped contracts; external API/UI/deployment proof remains separate |
| `stage4_green` | CI run #1712 on Stage 4 HEAD `f677c5f347f9e9522f950909b075a305ca26cce7` | GitHub Actions / commit | VERIFIED, subject to descendant-contract review |
| `stage5_green` | PR #246 merged; Stage 5 HEAD `e269cf80b4bcbf64ec5e8f855c48abd979fd4752` and merge commit `f677c5f347f9e9522f950909b075a305ca26cce7` | Git history / PR | VERIFIED |
| `stage6_green` | PR #251 merged; Stage 6 HEAD `585fb5684cf4f05b911c80463930278b4b64bcdf` | Git history / PR | VERIFIED |
| `side_doors_scanned` | Structural execution-surface guards and REAL authorization-factory consumer guard passed on descendant CI and are re-run by current CI | GitHub Actions / tests | VERIFIED for current audit target once fresh register commit CI passes |
| `ci_green` | CI #1800: full suite/build/container/smoke pipeline passed on `7a25cd40f369620bfb002ebeaefb6a60dcc11c51` | GitHub Actions | HISTORICAL; not current evidence for this target |
| `secrets_reviewed` | Secret-scanning/push-protection review; no repository-detected open provider-secret alerts were reported in the prior review | GitHub security settings | VERIFIED for repository scope; external deployment secrets remain outside repository evidence scope |
| `repository_governance` | Main branch governance was previously verified | GitHub repository settings | VERIFIED |

## Current rollback evidence

The rollback drill is now an executed artifact, not a documentation-only claim.

- Workflow: Stage 7 rollback drill.
- Run: #1, completed successfully.
- Commit exercised: `7a25cd40f369620bfb002ebeaefb6a60dcc11c51`.
- Artifact: `stage7-rollback-evidence`, artifact id `10526753950`.
- Drill scope: CI-only immutable-container rollback; it intentionally does **not** claim an external production rollback.
- The artifact records the known-good image, deliberately unhealthy candidate, observed failure state, restoration target, and `real_execution=false`.
- Therefore `rollback_tested` can be supported by this controlled recovery execution, but `external_production_rollback_proven` remains false.

## Stage 3 descendant evidence

Stage 3 consolidated HEAD `31c18b5ce51623c38205a27fb6d0c05481113b4b` is an ancestor of the Stage 7 target. Current CI on the descendant provides regression evidence for mapped contracts when the relevant tests are still present and executed.

Relevant mapped coverage includes production topology/state authority, DEMO market identity, controlled DEMO execution, recovery/reconciliation, and observability/identity contracts.

## Execution-surface finding

The audited execution boundaries remain:

- `execution/adapter_gateway.py`
- `execution/gateway.py`
- `execution/real_gateway.py`
- `execution/p125_sandbox_validation.py`
- `execution/demo_broker_port.py`
- `execution/demo_risk_dispatch_guard.py`

The REAL authorization surface has a low-level capability check: direct construction with public fields remains inactive, while the active factory requires the exact issuer capability. Structural tests reject new production consumers of that factory outside the dedicated issuer.

This is structural evidence, not proof of external broker or production behavior.

## Explicitly unresolved / requiring gate-specific proof

The following must not be represented as green merely because related code or documentation exists:

- `threat_model_reviewed`: the current threat-model artifact is repository evidence, but external infrastructure/threat assumptions remain outside code-only scope.
- `secrets_reviewed`: repository secret scanning does not prove that external deployment/broker/cloud secrets are configured correctly.
- `demo_real_separation_tested`: current code/config tests are strong, but end-to-end external API/UI/deployment evidence remains outside repository-only proof.
- `ci_green`: predecessor CI #1815 passed after the provenance fixes; a fresh run is required after this register refresh commit.

## Evidence inheritance rule

A descendant CI run may serve as evidence for an ancestor gate only when:

1. the descendant contains the ancestor;
2. the cited CI execution ran the relevant contract/tests;
3. no later change invalidated the relevant contract;
4. the evidence reference identifies the ancestor scope and descendant execution;
5. the claim is limited to what that execution actually proves.

A merged PR, PR number, documentation statement, or non-executed configuration value is not itself proof of a behavioral gate.

## REAL safety invariant

This register never enables REAL. Stage 7 readiness remains governance-only. REAL authorization remains a separate explicit control. The current issuer provenance is an in-process capability mechanism, not cryptographic human/operator authentication.

## Closure rule

Do not replace PENDING/UNRESOLVED entries with VERIFIED without a concrete, inspectable evidence reference. External production rollback, broker behavior, live IAM/network configuration, and live incident response remain operational evidence items and are not claimed here.
