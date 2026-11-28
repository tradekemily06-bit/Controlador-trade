# Six-area module and capability map

## Purpose and scope rule

This document consolidates the functional scope in `PROJECT_MASTER_SPEC.md`, the eight intelligence layers in `docs/ADVANCED_INTELLIGENCE_TARGET.md`, and the approved six-area application contract.

It is a **scope-preservation register**, not a declaration that every capability is already implemented or production-connected. Every item remains assigned to one of the six approved visible areas or to shared internal infrastructure. No seventh navigation area is introduced.

Status meanings:
- **Code present:** implementation and/or tests exist in the repository.
- **Partial integration:** code exists but is not fully connected to the standalone runtime, provider, frontend or persistent production environment.
- **External gate:** requires provider credentials, hosting, KMS, real device, user-owned Lovable deployment or other environment evidence.
- **Not yet evidenced:** the master specification requires the capability, but current code/CI is not enough to claim it.

## 1. Cabine de Comando

| Capability | Repository evidence | Honest status |
|---|---|---|
| Current operating state, signal, asset, timeframe and evidence score | `standalone_app.py`, `signal_engine.py`, `scoring.py`, `integration/market_timeframe_monitor.py` | Code present; live provider acceptance pending |
| COMPRA / VENDA / AGUARDAR and fail-closed decision state | `core/`, `signal_engine.py`, `filters.py`, `risk_manager.py` | Code present; no probability/profit guarantee |
| Current cycle, candle close, freshness and provider health | `data/provider_clock.py`, `integration/market_timeframe_monitor.py`, `integration/tenant_connection_timeframe_monitor.py` | Intraday cycle logic present; D1/W1 fail closed until real session calendar is injected |
| Risk state, kill switch and operational blockers | `risk_manager.py`, `core/`, `execution/`, `audit/` | Code/test foundation present; REAL remains disabled |
| Alerts and important changes | `integration/`, `core/` notification outbox and worker components | In-app/outbox foundation present; external push delivery not production-verified |
| Minimal/secret presentation mode | Existing Lovable presentation contract | Preserve existing behavior; browser-level acceptance pending |

## 2. Análise

| Capability | Repository evidence | Honest status |
|---|---|---|
| Market data: candles, quotes, volume/spread where supplied, freshness and gaps | `data/`, `integration/`, `analysis/` | Provider-neutral contracts and adapters present; live feed per broker/asset/timeframe still requires validation |
| Price action, trend, structure, volatility, momentum, support/resistance, patterns and pressure | `analysis/`, `signal_engine.py`, `scoring.py`, `filters.py` | Existing analytical modules retained; each feature must keep its own evidence and limitations |
| Multi-timeframe and closed-candle signal lifecycle | `integration/market_timeframe_monitor.py`, `integration/tenant_connection_timeframe_monitor.py` | M1/M5/M10/M15 coverage and isolation tests present; real provider session/calendar evidence pending |
| News event triage and affected-asset classification | `analysis/news_event_intelligence.py` | Deterministic triage only; not sentiment, direction or probability |
| RSS/Atom ingestion and evidence corroboration | `integration/rss_news_provider.py`, `analysis/news_evidence_corroboration.py`, `integration/news_polling_worker.py` | Polling and owner-scoped evidence code present; host source policies, DNS/IP pinning, full-article verification and hosted operation pending |
| Economic calendar, revisions and source provenance | `analysis/economic_calendar.py`, `integration/economic_calendar_ingestion.py` | Normalization, append-only observations and polling worker present; official central-bank/statistical-agency adapters and real ingestion schedule pending |
| Cross-asset/cross-market context graph | `docs/ADVANCED_INTELLIGENCE_TARGET.md` | Target requirement; persistent evidence-backed graph not yet evidenced as complete |
| Adversarial synthesis and counterevidence | `core/unified_intelligence.py`, existing context/decision components | Shared orchestration foundation present; complete multi-source conflict resolution remains partial |
| Forecast evaluation and calibration | Existing scoring/calibration modules under `core/` and `analysis/` | Diagnostics exist; no calibrated win/profit probability may be displayed without representative out-of-sample evidence |

## 3. Estudo

| Capability | Repository evidence | Honest status |
|---|---|---|
| Replay, backtest and simulator | `core/`, `test_replay_engine.py`, `test_backtest_engine.py` | Code and automated coverage present; validate all UI workflows against the current Lovable app |
| Study library, concepts, patterns and recurring errors | `core/`, `analysis/`, learning components | Existing learning/study foundations retained; full content ingestion and UX acceptance pending |
| Hypotheses and validation workflow | P51–P53 learning contracts in `core/` | Factual evidence/hypothesis boundary present; hypothesis validation and controlled promotion remain incomplete |
| Video analysis: transcription, visual extraction, claims and testable hypotheses | `PROJECT_MASTER_SPEC.md` | Required scope preserved; end-to-end video ingestion/analysis is not yet evidenced as complete |
| Performance statistics by market condition and timeframe | `core/`, `audit/`, learning/result modules | Historical/result primitives exist; only reconciled outcomes may train learning; full representative dataset remains pending |

## 4. Reserva Fiscal

| Capability | Repository evidence | Honest status |
|---|---|---|
| Separate Brazil and international queues | `finance/`, fiscal routes and owner-scoped storage | Code present; preserve separate classifications |
| Manual records, evidence, periods and planning percentage | `finance/`, `integration/` | Code present; this is a planning organizer, not a legal tax calculator |
| Foreign-currency records and pending classification | `finance/` | Code present; no automatic generic tax percentage or unverified conversion |
| History, export and owner isolation | `finance/`, `security/`, tests | Code/test foundation present; production shared database and frontend acceptance pending |

## 5. Assistente do Ecossistema

| Capability | Repository evidence | Honest status |
|---|---|---|
| Read-only questions, explanations and summaries | `assistant/`, `integration/`, `standalone_app.py` | Code present; provider key and production configuration remain external |
| Explicit consent, owner-scoped history and sanitized context | `assistant/`, `security/`, tests | Code/test foundation present |
| Research and evidence explanation | `core/unified_intelligence.py`, `analysis/` | Shared orchestration exists; source coverage and full context integration remain partial |
| No orders, no money movement, no REAL authority | API and execution safety boundaries | Mandatory invariant; never delegated to the assistant |

## 6. Central

| Capability | Repository evidence | Honest status |
|---|---|---|
| Broker/platform connections and provider status | `integration/`, `data/` | MT5 relay and cTrader adapter foundations present; live credentials, account handshakes and each provider's interval support require external proof |
| User settings, preferences and account/tenant controls | `saas/`, `security/`, `integration/` | Code foundation present; production identity and shared persistence pending |
| Notifications, devices, subscription revocation and delivery status | `integration/`, `security/`, `web/pwa/` | Outbox, Web Push primitives and workers present; production KMS/VAPID, DNS pinning, hosted worker and physical-device tests pending |
| Audit, history, security events and access controls | `audit/`, `security/`, `core/` | Code/test foundation present; shared durable production audit pending |
| Backup, restore, retention and recovery | `core/sqlite_backup_service.py`, `core/sqlite_backup_scheduler.py`, `integration/standalone_foundation_status.py` | Local backup/restore and readiness present; off-host backups, shared DB, scheduled hosted backup and restore drill pending |
| Internal admin and operational diagnostics | `standalone_app.py`, `integration/`, `core/` | Code foundation present; operator-facing deployment acceptance pending |

## Shared internal capabilities — not visible navigation areas

These capabilities serve all six areas and must remain internal infrastructure:

- identity, tenant/subject isolation, authorization and secret management;
- provider registry, market-data normalization, time synchronization and freshness;
- decision engine, confluence, evidence scoring and abstention;
- risk gate, kill switch, execution gateway and order/REAL safety boundaries;
- immutable intent, lifecycle, reconciliation, factual outcome and audit;
- decision memory, learning evidence, hypotheses, model/rule versioning and calibration;
- context/news/calendar provenance, event deduplication and conflict tracking;
- notification outbox, worker leases, idempotency, retries and dead-letter handling;
- backup, restore, health/readiness, metrics, logs and incident recovery.

## Eight advanced-intelligence layers retained

| Layer | Assigned area(s) | Current boundary |
|---|---|---|
| 1. Evidence ingestion | Análise / Central | Market contracts, RSS and calendar primitives exist; complete official feeds and live provider coverage pending |
| 2. Normalization and provenance | Análise / internal data layer | Partial implementation; all feeds still need source-specific adapters and validation |
| 3. Context graph | Análise / internal intelligence | Not yet complete; must retain evidence and temporal validity |
| 4. Independent analysis | Análise | Existing technical and event modules; full independent macro/cross-asset/liquidity analyzers pending |
| 5. Adversarial synthesis | Análise / Assistente | Partial; conflicting evidence must remain explicit and support abstention |
| 6. Forecast evaluation | Análise / Estudo | Diagnostics exist; calibrated probabilities remain unavailable pending representative out-of-sample validation |
| 7. Persistent learning and audit | Estudo / Central / internal | Learning and audit primitives exist; production shared tenant storage and promotion controls remain pending |
| 8. Explanation and alerts | Cabine / Análise / Central | Explanation and alert foundations exist; complete source-linked UI and real-device push acceptance pending |

## Explicit exclusions and invariants

- Exactly six visible areas; no seventh Memory or Intelligence tab.
- Decision memory, audit, learning, context graph, safety and provider infrastructure remain shared internal capabilities.
- No FOMO feature, urgency manipulation or fabricated countdown.
- No EA dependency; the application remains standalone.
- No Lovable visual redesign or replacement.
- SIMULAÇÃO only; REAL dispatch, order submission and money movement remain disabled in this foundation.
- A score is evidence strength, not a guaranteed win probability.
- No source, feed, adapter, polling worker or CI result is to be described as live/production-connected without environment evidence.

## Source of scope truth

- `PROJECT_MASTER_SPEC.md` — full functional and architectural scope.
- `docs/ADVANCED_INTELLIGENCE_TARGET.md` — eight intelligence layers and measurable acceptance gates.
- `docs/STANDALONE_COMPLETION_ROADMAP.md` — integration/deployment exit evidence.
- `docs/IMPLEMENTATION_COMPLETION_LEDGER.md` — per-front implementation and validation state.

This map is additive. It does not invent P54+ milestones and does not change the approved interface.
