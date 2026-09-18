# P3 — Durable Persistence / Crash-Safety Final Matrix

Status: audit branch only; not merged to main.

## Crash-window matrix

| Crash/failure boundary | Durable state after failure | Restart/retry behavior | Replay? | Recovery path | Evidence |
|---|---|---|---|---|---|
| Before lifecycle PENDING | no lifecycle/ledger state | new request may start | only if request was never durably admitted | normal start | gateway tests |
| After lifecycle PENDING, before ledger reserve | lifecycle=PENDING | blocked/REQUIRES_RECONCILIATION | No | verify lifecycle, repair only from durable authority | test_real_lifecycle_pending_before_ledger_reserve_failure_blocks_restart_without_dispatch |
| After ledger RESERVED, before broker call | ledger=RESERVED; lifecycle=PENDING | UNKNOWN / reconciliation required | No | reconcile existing request | gateway/recovery tests |
| Broker throws/timeout | ledger=UNKNOWN; lifecycle=UNKNOWN | UNKNOWN; no dispatch on retry | No | external reconciliation | test_real_executor_exception_persists_unknown_and_restart_blocks_adapter |
| Broker accepts, external ID missing | ledger=UNKNOWN; lifecycle=UNKNOWN | no replay | No | manual/query-by-request-id reconciliation when supported | test_real_accepted_without_external_id_marks_both_authorities_unknown |
| Broker accepts, before external-ID bind | ledger=RESERVED; lifecycle=UNKNOWN/PENDING depending boundary | no replay | No | query broker by durable request/client ID if adapter supports it | test_real_external_id_bind_failure_is_non_replayable_after_restart |
| External ID bound, before ledger terminal | ledger=RESERVED + external_id | no replay | No | reconcile exact external ID | gateway/reconciliation tests |
| Ledger terminal, before lifecycle terminal | ledger terminal; lifecycle UNKNOWN | blocked; lifecycle repair/reconciliation | No | durable ledger projection repair | test_real_lifecycle_persistence_failure_after_ledger_terminal_blocks_restart |
| Lifecycle terminal successfully persisted | both terminal and compatible | safe resume | No replay | normal recovery | lifecycle/recovery tests |
| Hard process interruption during broker acceptance | durable pre-call state remains; broker outcome uncertain | reconciliation required; retry cannot dispatch | No | external reconciliation | test_real_process_interrupt_after_broker_acceptance_never_replays |
| Recovery worker races execution worker | one durable authority wins; second observes durable state | reconciliation remains idempotent | No | exact external identity reconciliation | test_recovery_worker_racing_execution_worker_never_replays_uncertain_request |

## Cross-authority divergence matrix

| Divergence | Automatic resume | Allowed repair |
|---|---:|---|
| lifecycle ACCEPTED + ledger missing | No | only from verified durable ledger/external evidence |
| lifecycle REJECTED + ledger missing | No | same |
| lifecycle terminal vs incompatible ledger terminal | No | destructive overwrite refused |
| ledger terminal + lifecycle missing | No | lifecycle projection repair from ledger |
| ledger RESERVED/UNKNOWN + lifecycle UNKNOWN | No | verified external reconciliation |
| lifecycle-only PENDING/UNKNOWN | No | never creates a REAL ledger retroactively |
| legacy terminal ledger without external_id + arbitrary external fact | No | rejected |
| conflicting external_id | No | rejected |
| duplicate persisted external_id | No | corruption / startup failure |

## Retry invariants

1. A request that reached durable admission is never released for a fresh broker dispatch merely because persistence failed afterward.
2. UNKNOWN and RESERVED are never implicitly promoted to terminal states.
3. Terminal ledger/lifecycle states cannot be silently overwritten.
4. Reconciliation is read-only with respect to broker execution; it never submits an order.
5. Reconciliation retries are idempotent.
6. Cross-store partial completion remains fail-closed.
7. External identity must match exactly before broker evidence can reconcile an uncertain request.

## Atomicity / locking matrix

- JSON writes use temporary file + flush/fsync + replace.
- Unix uses fcntl.flock; Windows uses msvcrt.locking.
- Read/modify/write mutations are performed under the same file lock.
- Replace failure preserves the previous target.
- Post-replace directory-fsync failure is treated as an ambiguous commit and must be followed by durable reread, not assumed rollback.
- Concurrent lifecycle writers and concurrent ledger reservations are tested.
- Windows CI now runs both durable persistence and P3 execution crash/concurrency tests.

## Remaining integration dependency

The only material external integration dependency is broker-side read-only lookup by durable request/client-order identity for the crash window where the broker may have accepted an order but the external ID was not durably captured. The core deliberately fails closed when that capability is unavailable; it does not invent or retry the order.

## Persistence surfaces classified

- ExecutionLedger: execution authority.
- ExecutionLifecycleStore: execution lifecycle authority/projection.
- OperationMemoryStore: operational memory, durable but not execution authority.
- OperationalSafetyStore: safety/audit state.
- RuntimeCheckpointStore: restart checkpoint, never an execution authority.
- DecisionAudit: decision/audit trail.
- PersistentOperationalRecorder: coordinated audit + memory persistence.
- durable_json: atomic/locked persistence primitive.
- security_audit SQLite: bounded auxiliary security trail; best-effort, not execution authority.
- report export writes: export artifact, not execution authority.

## P3 completion gate

Part 3 should be marked complete only when the branch CI is green after the final persistence/Windows changes and the external broker lookup dependency remains explicitly fail-closed.
