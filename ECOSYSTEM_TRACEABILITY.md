# Controlador Trading — Traceability and Unmerged Work Inventory

Status: **audit in progress (2026-09-23)**

This file prevents work from being treated as lost or silently dropped while the day-to-day DEMO/mobile consolidation is completed.

## 1. Current integration chain
- `main`: source of truth for already merged work.
- PR #275 `day-to-day-demo-runtime`: daily DEMO execution path on the shared gateway. CI run 4194 passed.
- PR #277 `feat/universal-mobile-web`: mobile/tablet/web hardening. Its base is PR #275 so the DEMO runtime is not abandoned. CI run 4229 passed on the head commit.
- PR #277 is not merged and GitHub currently reports it as not mergeable while the changed base is being reconciled.
- No stage is complete until the combined result is tested.

## 2. User requirements that must remain traceable

### Operational cockpit
- COMPRA / VENDA / AGUARDAR
- score/quality/strength and explanation
- candle-close confirmation
- filters and market/context readings
- DEMO/SIMULAÇÃO permanently explicit
- REAL blocked by default and not enabled by the UI
- Risk Gate and fail-closed behavior
- execution state, reconciliation, UNKNOWN, duplicate protection
- operational memory and WIN/LOSS/DRAW/OPEN/VOID outcomes
- audit trail
- kill switch/emergency stop must remain an operational safety control, not a decorative label

### Market-reading / methodology vocabulary
- tendência, estrutura
- suporte/resistência
- topos/fundos
- volume
- rompimento/pullback
- pavio/rejeição
- retirada de pavio
- vela comando/força
- GAB
- DDT
- pressão alta/baixa
- taxa dívida
- other relevant context may be considered; the UI must not imply that a concept is a validated live rule merely because it is listed.

### Study / learning ecosystem
- Laboratório
- Replay
- simulator/training activities
- operational memory/statistics
- visual material/video analysis when supplied
- learning resources/sources/observations/activities/attempts
- discovery/context separated from execution authority
- learning must never authorize trading

### Cross-device / day-to-day
- one ecosystem, not separate mobile/desktop logic
- device changes presentation/geometry only
- operational state, decision, risk, memory, permissions and execution authority remain device-invariant
- preferences persist in the runtime, not browser local storage
- mobile/tablet/notebook/desktop and portrait/landscape support
- PWA/installability support without changing trading logic

## 3. Concrete work found outside the current integration chain

These are real GitHub branches/PRs, not assumed features. They must not be forgotten; they also must not be merged blindly.

### Day-to-day / deployment
- PR #272 `feat/windows-persistent-launcher`: Windows persistent startup.
- PR #276 `fix/windows-autostart-hardening`: hardens #272 by pinning Python resolution and binding the launcher to 127.0.0.1. CI currently passed.
- PR #273 `feat/persistent-mt5-runtime`: persistent read-only MT5 market-data runtime. CI currently passed.
- PR #271 `fix/windows-file-locking`: native Windows cross-process file locking. Important for durable safety state on Windows; currently based on `release/real-mode-selectable`, so it requires ancestry/integration review before use.
- PR #274 `feat/mt5-real-execution-bridge`: guarded MT5 REAL adapter. This is intentionally not part of the day-to-day DEMO path and must remain behind the separate REAL authorization/safety frontier. It is not a missing DEMO feature.

### Security / reliability audit work
- PR #269: Part 7.2 REAL evidence/provenance and broker correlation hardening.
- PR #268: combined Part 7.1 integrity hardening, including Part 6 recovery/lifecycle work and Semgrep findings.
- PR #266: Part 6 recovery consistency/lifecycle persistence hardening.
- PR #263: Part 4 execution identity, lifecycle and recovery hardening.
- PR #252: Stage 7 release governance rebased on Stage 6.
- PR #241: multi-device session registry.
- PR #240: durable technical-incident execution barrier; currently non-mergeable and explicitly still in audit.
- PR #239: deep tenant/state isolation and execution hardening.
- PR #238: deep HTTP data-integrity/build hardening.

Older open audit/stage PRs also exist (#267, #265, #264, #262, #261, #260, #259, #258, #257, #255, #254, #253, #249, #244, #243). Their existence is recorded here so no functionality is assumed lost; they require comparison against the latest validated chain before any consolidation.

## 4. Present in GitHub != integrated

A branch or PR containing a feature is not the same thing as that feature being part of the current runnable ecosystem. Before adopting any item we must:
1. compare it with the current base and newer security fixes;
2. identify whether a later PR supersedes it;
3. resolve ancestry/base conflicts;
4. run targeted tests;
5. run full CI;
6. review real-failure behavior;
7. perform an independent second scan;
8. run CI again.

No old PR is to be merged merely because it has useful-looking code.

## 5. Known current gaps discovered during this audit
- PR #277 is not yet integrated with main; its base intentionally depends on PR #275.
- The current web page visibly labels the kill switch, but this audit has not yet proven that an immediately reachable actionable kill-switch control is wired into the day-to-day cockpit. This remains an open verification item.
- The full web API/component reachability matrix is still being audited. Components currently present are onboarding, notifications and leverage/media; they must all remain mounted or be explicitly classified as backend-only/obsolete.
- Runtime-local persistence is not the same as hosted multi-user cloud persistence. Image/preferences sharing currently means devices using the same runtime, not a completed internet SaaS tenancy model.
- A true production multi-user identity/session/tenant boundary is not considered complete merely because a local multi-device/session branch exists.
- The mobile contract must be verified against the combined PR #275 + #277 result, not only against the head branch in isolation.

## 6. Safety frontier
The day-to-day path remains DEMO/SIMULAÇÃO. REAL must remain blocked unless a future, separately reviewed, explicitly authorized production boundary is completed. Learning, discovery, news/context, preferences, health/status, notifications, media customization and mobile presentation must never grant execution authority.

## 7. Next audit order

Do not jump stages. Finish the current day-to-day/mobile consolidation first:
1. verify combined #275 + #277 tree;
2. verify every web component mount;
3. verify frontend API calls against backend routes;
4. verify demo execute path reaches the shared gateway without bypasses;
5. verify kill-switch reachability and enforcement;
6. verify device-invariant state and persistence;
7. targeted tests;
8. full CI;
9. real-failure analysis;
10. independent second scan;
11. full CI again;
12. only then close this stage and select the next unmerged work item from this inventory.

This inventory is deliberately a traceability map, not a declaration that all listed work is already complete.


## 8. Deep inventory findings — 2026-09-23

### 8.1 GitHub branch census
A complete branch search returned **393 branch refs** (pages 1–4). They are not all independent pending features. The branch families include historical P2–P26 work; P54–P128 learning/knowledge/adaptation/governance work; P127 broker/DEMO integration variants; P128 learning/market-reading/context variants; P129–P150 asset suitability, analysis, risk, learning handoff, onboarding and notification work; Stage 2–7 consolidation/release branches; security/tenant/transport/audit branches; and current day-to-day/mobile/deployment branches.

The existence of these refs is now explicitly accounted for. They must be classified by ancestry/PR/history before reuse; branch-name existence is not treated as proof that code is missing.

### 8.2 Roadmap traceability correction
The repository contains concrete definitions and implementation artifacts beyond P53. Verified evidence includes:
- P54–P60: controlled hypothesis validation → trusted knowledge → controlled use → knowledge memory/audit/lab;
- P61–P63: controlled adaptation proposal/application/factual audit;
- P64–P66: activation/observation/evaluation;
- P67–P70: consolidation/disposition/eligibility/closure;
- P71–P74: audit/archive/admission/handoff;
- P75–P79: handoff validation/context/audit/hypothesis/admission;
- P80–P85: controlled validation/promotion to trusted knowledge;
- P86–P89: governance/audit/controlled-use authorization/closure;
- P90–P95: controlled-use cycle and operational admission;
- P96–P99: operational feedback cycle;
- P100–P105: audit/archive/readiness/context/hypothesis/admission;
- P106–P110: validation specification/record/result/decision;
- P111–P119: pre-REAL audit, explicit REAL authorization boundary, multi-broker architecture, fail-closed REAL barrier, shadow/sandbox validation, release governance, controlled REAL admission and factual external-result observation;
- P120–P126: REAL result ambiguity, external reconciliation, broker-neutral market/order/session contracts, DEMO/Sandbox validation and pre-REAL security validation;
- P127: IC Markets MT5 DEMO integration;
- P128: integrated market-learning boundary; a separate cTrader DEMO OAuth/session boundary is documented.

Therefore the current master spec statement that P53 is the last confirmed roadmap milestone is **stale documentation**, not evidence that P54+ is missing. Do not invent replacement text in the master spec; reconcile it later from the versioned plans/addenda and merged history.

### 8.3 P129–P150 historical chain
The GitHub history also contains a later product chain:
P129 asset universe → P130 execution-path hardening → P131 senior expertise → P132/P133 asset suitability → P134 leverage/point-value/media → P135/P136 senior analysis boundary/integration → P137 operational-risk bridge → P138/P139 DEMO result-to-learning/reconciliation → P140 legacy execution admission hardening → P141–P147 onboarding/notification UI → P148 expanded Python compilation → P149 protected internal updates.

PRs #226–#236 show P138–P149 were implemented/merged into main; PR #237 is a later documentation synchronization proposal and remains open. P150 appears as a branch name but no corresponding PR was found in the searched PR inventory, so it remains **unclassified**, not assumed complete or missing.

### 8.4 Current day-to-day/mobile frontier
- #275 remains open/draft, base main, head `24e171c07d29c0aea10e07cdd72bfda13e201b92`.
- #277 remains open/non-draft, base #275's head, current head `d2deac39d2b7245b69b753dfbfc6e8db4174dc30`.
- The current #277 head has **pending/no reported commit statuses** at the time of this inventory. Earlier passing CI referenced in this file belongs to an earlier head and must not be reused as proof for the current head.
- #277 is reported non-mergeable at present. No merge should be attempted during this inventory phase.
- The actionable Kill Switch is present in the current #277 tree and is mounted by `app.py`; the earlier “decorative-only” gap is therefore **resolved in the mobile branch code**, pending targeted/full validation.

### 8.5 Deployment/integration items that remain parked, not forgotten
- #272 Windows persistent launcher;
- #276 Windows autostart hardening layered over #272;
- #271 Windows cross-process locking (base is `release/real-mode-selectable`, so ancestry reconciliation is required before adoption);
- #273 persistent read-only MT5 market-data runtime;
- #274 guarded MT5 REAL bridge, intentionally outside the day-to-day DEMO path;
- #238/#239 HTTP/data-integrity and tenant/state isolation hardening;
- #240 durable technical-incident barrier;
- #241 multi-device session registry;
- #252 Stage 7 governance;
- #254/#255/#260/#261/#262/#263/#264/#265/#266/#267/#268/#269 audit/security work.

These are classified as **parked candidates for later reconciliation**, not silently discarded.

### 8.6 Documentation drift that must not be mistaken for code loss
Two concrete drift points are recorded:
1. `PROJECT_MASTER_SPEC.md` still says P53 is the last confirmed milestone despite versioned P54–P128 roadmap artifacts and later P129–P149 history.
2. `README.md` on the mobile branch describes the current core/interface as implemented, while #275/#277 and several deployment/security branches are still unmerged. That wording must be treated as describing the branch's implemented surface, not as proof that the entire GitHub work inventory is integrated.

### 8.7 Inventory rule going forward
No branch/PR/plan is considered “lost” merely because it is not in the current runnable chain. Before the next implementation step, each relevant item must receive one of:
**INTEGRATED / SUPERSEDED / PARKED-FOR-LATER / HISTORICAL-VALIDATED / INTENTIONALLY-SEPARATE / NEEDS-RECONCILIATION**.

Only after this classification is complete will the inventory be considered closed.


## 9. Workbench organization — 2026-09-23

### Current rule
This branch is being used as the organized workbench for the current inventory. No new product feature is being declared complete from this document.

### Work buckets
**A — CURRENT CHAIN / VALIDATE BEFORE ADVANCE**
- #275 DEMO daily runtime
- #277 universal mobile/web
- current mounted cockpit components
- current backend API surface
- current device-invariant persistence changes
- current kill-switch implementation

**B — PARKED FOR RECONCILIATION**
- #272/#276 Windows launcher/autostart
- #273 MT5 read-only market-data runtime
- #271 Windows cross-process locking
- #241 multi-device session registry
- #238/#239 HTTP/data-integrity and tenant/state isolation
- #240 durable technical-incident barrier
- #252 Stage 7 governance
- #254/#255/#260/#261/#262/#263/#264/#265/#266/#267/#268/#269 security/audit lineage
- #274 guarded MT5 REAL bridge

**C — HISTORICAL / TRACEABILITY**
- P54–P128 roadmap artifacts
- P129–P149 merged product chain
- older Stage/audit branches and their superseded variants
- P150 branch remains unclassified until its exact intent is established

### Do-not-lose rules
1. Do not delete or merge a parked branch merely because a newer branch exists.
2. Do not cherry-pick a parked PR until ancestry, duplicate changes, tests, and security implications are checked.
3. Do not treat branch existence as proof of missing functionality.
4. Do not treat README/master-spec wording as proof of implementation status when Git history disagrees.
5. Do not call #277 validated until its current HEAD receives fresh CI.
6. Do not bring REAL execution work into the DEMO day-to-day chain without the existing REAL security/reconciliation gates.
7. Keep DEMO/REAL authority, kill switch, ledger/lifecycle, reconciliation, and recovery boundaries explicit.
8. Keep learning/context/news/media informational unless a separately validated rule explicitly admits them.
9. Any newly discovered item must be assigned a bucket before implementation continues.

### Next work order — inventory only
1. Complete PR/branch-to-current-tree reconciliation.
2. Resolve P150.
3. Reconcile stale roadmap/master documentation.
4. Run the independent second orphan/feature scan.
5. Produce the final “nothing relevant left unclassified” inventory.
6. Only then begin implementation/validation work.

This section is an organizational checkpoint, not a completion claim.


## 10. Deep ancestry/reconciliation checkpoint — 2026-09-23

### Branch universe
The repository currently exposes **393 branch refs** across the four branch-search pages. The census spans P2–P26 foundation/recovery; P36–P53 market context, automation and learning; P54–P126 controlled learning/REAL/reconciliation; P127/P128 broker, market-learning and senior-context variants; P129–P150 asset suitability, senior analysis, risk, learning handoff and onboarding; Stage 2–7 consolidation/release; security/tenant/transport/audit lines; and current DEMO/mobile/deployment lines.

The large number of variants is itself a reconciliation requirement. Names such as final, ready, current, v2, v3, x, and stop are not evidence that a branch is authoritative.

### P150 finding
p150/saas-onboarding-status was compared directly with main and is identical: ahead 0, behind 0, total commits 0. Therefore P150 currently has no unique delta relative to main. Classification: HISTORICAL-VALIDATED / NO-DELTA.

### Current day-to-day/mobile ancestry finding
day-to-day-demo-runtime is 140 commits ahead of main. feat/universal-mobile-web is 46 commits ahead of main. However, PR #277 explicitly targets day-to-day-demo-runtime, and its current HEAD is fa85db23ebc5c638ca24757348ba42eae3d6a38e, while its base is 24e171c07d29c0aea10e07cdd72bfda13e201b92.

The direct comparison day-to-day-demo-runtime -> feat/universal-mobile-web reports status DIVERGED, mobile ahead 46, mobile behind 140. This explains the current non-mergeable state of #277. It must be treated as an ancestry/reconciliation issue, not as evidence that either side's functionality should simply be discarded.

### Current implication
For now, preserve both lines. The DEMO operational runtime remains its own preserved candidate; universal mobile/web remains its own preserved candidate. No automatic cherry-pick or merge is authorized by this inventory. Before implementation continues, the two lines must be reconciled deliberately so the final chain does not lose DEMO execution, journal, lifecycle, ledger, recovery, risk, or safety work.

### Other direct comparisons already checked
- fix/windows-autostart-hardening: 5 commits ahead of main.
- feat/persistent-mt5-runtime: 3 commits ahead of main.
- feat/mt5-real-execution-bridge: 170 commits ahead of main.
- fix/windows-file-locking: 832 commits ahead of main and therefore represents a much broader historical/security line, not merely a one-file locking patch.

These are preserved as separate candidates until ancestry/content overlap is reconciled.

This checkpoint intentionally does not merge, close, delete, or declare any candidate complete.
