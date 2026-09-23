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
