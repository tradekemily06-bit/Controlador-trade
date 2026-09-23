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
