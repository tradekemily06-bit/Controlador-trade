from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


class RecoveryState(str, Enum):
    FRESH = "FRESH"
    SAFE_TO_RESUME = "SAFE_TO_RESUME"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"
    INVALID = "INVALID"


@dataclass(frozen=True)
class RecoveryAssessment:
    state: RecoveryState
    checkpoint: RuntimeCheckpoint | None
    pending_request_ids: tuple[str, ...]
    unknown_request_ids: tuple[str, ...]
    message: str

    @property
    def can_resume(self) -> bool:
        return self.state in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME)


class RecoveryCoordinator:
    """Assesses restart state without replaying or executing any order."""

    _MAX_CHECKPOINT_CLOCK_SKEW = timedelta(minutes=5)

    def __init__(
        self,
        *,
        checkpoint_store: RuntimeCheckpointStore,
        lifecycle_store: ExecutionLifecycleStore,
        execution_ledger: ExecutionLedger,
        memory: OperationMemory,
        expected_session_id: str | None = None,
    ) -> None:
        if not isinstance(checkpoint_store, RuntimeCheckpointStore):
            raise ValueError("checkpoint_store inválido.")
        if not isinstance(lifecycle_store, ExecutionLifecycleStore):
            raise ValueError("lifecycle_store inválido.")
        if not isinstance(execution_ledger, ExecutionLedger):
            raise ValueError("execution_ledger inválido.")
        if not isinstance(memory, OperationMemory):
            raise ValueError("memory inválida.")
        self.checkpoint_store = checkpoint_store
        self.lifecycle_store = lifecycle_store
        self.execution_ledger = execution_ledger
        self.memory = memory
        if expected_session_id is not None and (
            not isinstance(expected_session_id, str)
            or not expected_session_id.strip()
            or expected_session_id != expected_session_id.strip()
        ):
            raise ValueError("expected_session_id inválido ou não canônico.")
        self.expected_session_id = expected_session_id

    def assess(self, *, ignore_request_id: str | None = None) -> RecoveryAssessment:
        """Assess durable recovery, optionally excluding the request currently being admitted.

        The excluded request is still governed by its own atomic ledger/lifecycle
        admission checks. This narrow exception prevents a final pre-executor
        recheck from treating the gateway's own RESERVED/PENDING admission as a
        recovery fault, while all other uncertain cross-store state remains
        blocking.
        """
        if ignore_request_id is not None and (
            not isinstance(ignore_request_id, str) or not ignore_request_id.strip() or ignore_request_id != ignore_request_id.strip()
        ):
            raise ValueError("ignore_request_id inválido.")
        ignored_id = ignore_request_id if ignore_request_id is not None else None
        # Recovery is a cross-store read. Each authority is individually locked,
        # but there is no filesystem-level transaction spanning checkpoint,
        # lifecycle and ledger. Take a stable snapshot instead of allowing a
        # concurrent writer to produce a mixed-time view that could look safe.
        snapshot = None
        for _ in range(3):
            try:
                first = (
                    self.checkpoint_store.load(),
                    self.lifecycle_store.records(),
                    self.execution_ledger.statuses(),
                )
                second = (
                    self.checkpoint_store.load(),
                    self.lifecycle_store.records(),
                    self.execution_ledger.statuses(),
                )
            except ValueError as exc:
                return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")
            if first == second:
                snapshot = first
                break
        if snapshot is None:
            return RecoveryAssessment(
                RecoveryState.REQUIRES_RECONCILIATION,
                None,
                (),
                (),
                "estado durável mudou durante a avaliação; retomada recusada até obter snapshot estável.",
            )

        checkpoint, lifecycle, ledger_statuses = snapshot
        ledger_ids = set(ledger_statuses)
        ledger_uncertain = {
            request_id
            for request_id, status in ledger_statuses.items()
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
            and request_id != ignored_id
        }

        lifecycle_by_id = {record.request_id: record.state for record in lifecycle}

        if checkpoint is not None:
            if self.expected_session_id is not None and checkpoint.session_id != self.expected_session_id:
                return RecoveryAssessment(RecoveryState.INVALID, checkpoint, (), (), "checkpoint pertence a outra sessão; retomada recusada.")

            if checkpoint.last_request_id is not None:
                if checkpoint.last_request_id not in ledger_ids and checkpoint.last_request_id not in lifecycle_by_id:
                    return RecoveryAssessment(RecoveryState.INVALID, checkpoint, (), (), "checkpoint referencia request_id inexistente nas autoridades duráveis.")
                associated_lifecycle = next((record for record in lifecycle if record.request_id == checkpoint.last_request_id), None)
                if associated_lifecycle is not None:
                    checkpoint_aware = (checkpoint.updated_at.tzinfo is not None and checkpoint.updated_at.utcoffset() is not None)
                    lifecycle_aware = (associated_lifecycle.updated_at.tzinfo is not None and associated_lifecycle.updated_at.utcoffset() is not None)
                    if checkpoint_aware != lifecycle_aware:
                        return RecoveryAssessment(RecoveryState.INVALID, checkpoint, (), (), "checkpoint e lifecycle usam regimes de timezone diferentes.")
                    if checkpoint.updated_at < associated_lifecycle.updated_at:
                        return RecoveryAssessment(RecoveryState.INVALID, checkpoint, (), (), "checkpoint está desatualizado em relação ao lifecycle durável associado.")

            now = datetime.now(checkpoint.updated_at.tzinfo) if checkpoint.updated_at.tzinfo is not None else datetime.now()
            if checkpoint.updated_at > now + self._MAX_CHECKPOINT_CLOCK_SKEW:
                return RecoveryAssessment(RecoveryState.INVALID, checkpoint, (), (), "checkpoint está no futuro além da tolerância de relógio.")

        pending = tuple(
            sorted(
                r.request_id
                for r in lifecycle
                if r.state is ExecutionLifecycleState.PENDING and r.request_id != ignored_id
            )
        )
        unknown = tuple(
            sorted(
                r.request_id
                for r in lifecycle
                if r.state is ExecutionLifecycleState.UNKNOWN and r.request_id != ignored_id
            )
        )

        inconsistent = [
            r.request_id
            for r in lifecycle
            if (
                r.request_id not in ledger_ids
                or (
                    r.state is ExecutionLifecycleState.ACCEPTED
                    and ledger_statuses.get(r.request_id)
                    not in (ExecutionLedgerStatus.ACCEPTED, ExecutionLedgerStatus.RECONCILED_EXECUTED)
                )
                or (
                    r.state is ExecutionLifecycleState.REJECTED
                    and ledger_statuses.get(r.request_id)
                    not in (ExecutionLedgerStatus.REJECTED, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED)
                )
                or (
                    r.state is ExecutionLifecycleState.PENDING
                    and ledger_statuses.get(r.request_id)
                    in (
                        ExecutionLedgerStatus.ACCEPTED,
                        ExecutionLedgerStatus.REJECTED,
                        ExecutionLedgerStatus.RECONCILED_EXECUTED,
                        ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                    )
                )
            )
        ]
        orphaned_terminal_ledger = [
            request_id
            for request_id, status in ledger_statuses.items()
            if status in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            )
            and request_id not in lifecycle_by_id
            and request_id != ignored_id
        ]
        if unknown or pending or inconsistent or ledger_uncertain or orphaned_terminal_ledger:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("lifecycle/ledger inconsistente requer reconciliação")
            if ledger_uncertain:
                details.append("ledger RESERVED/UNKNOWN requer reconciliação")
            if orphaned_terminal_ledger:
                details.append("ledger terminal sem lifecycle requer reconciliação")
            return RecoveryAssessment(
                RecoveryState.REQUIRES_RECONCILIATION,
                checkpoint,
                pending,
                unknown,
                "; ".join(details),
            )

        state = RecoveryState.FRESH if checkpoint is None else RecoveryState.SAFE_TO_RESUME
        message = "nenhum estado pendente; retomada segura sem replay automático" if checkpoint else "nenhum checkpoint; sessão pode iniciar com segurança"
        return RecoveryAssessment(state, checkpoint, (), (), message)

    def reconcile_terminal_lifecycle(
        self,
        request_id: str,
        *,
        updated_at: datetime,
        message: str = "",
    ) -> ExecutionLifecycleRecord:
        """Repair lifecycle-only divergence from an already terminal durable ledger.

        This is internal consistency repair, not broker reconciliation: it never
        changes the ledger and never dispatches an order. The ledger terminal
        state is the source of truth for the lifecycle projection.
        """
        if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
            raise ValueError("request_id não pode ser vazio ou não canônico.")
        if not isinstance(updated_at, datetime):
            raise ValueError("updated_at inválido.")

        # Repair shares the same request boundary as REAL dispatch and broker
        # reconciliation, so a repair worker cannot race identity/state recovery.
        with self.execution_ledger.real_execution_lock():
            # Lifecycle repair changes global recovery admissibility, so it must
            # share the same barrier as REAL dispatch and reconciliation.
            with self.execution_ledger.request_execution_lock(request_id):
                ledger_status = self.execution_ledger.status(request_id)
                target = {
                    ExecutionLedgerStatus.ACCEPTED: ExecutionLifecycleState.ACCEPTED,
                    ExecutionLedgerStatus.REJECTED: ExecutionLifecycleState.REJECTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED: ExecutionLifecycleState.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED: ExecutionLifecycleState.REJECTED,
                }.get(ledger_status)
                if target is None:
                    raise ValueError("somente estados terminais do ledger podem reparar o lifecycle.")

                current = self.lifecycle_store.get(request_id)
                if current is not None and current.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
                    if (
                        (current.state is ExecutionLifecycleState.ACCEPTED and target is ExecutionLifecycleState.ACCEPTED)
                        or (current.state is ExecutionLifecycleState.REJECTED and target is ExecutionLifecycleState.REJECTED)
                    ):
                        return current
                    raise ValueError("lifecycle terminal diverge do ledger; reparo destrutivo recusado.")

                repair = ExecutionLifecycleRecord(
                    request_id,
                    target,
                    updated_at,
                    message or f"lifecycle alinhado ao estado terminal durável do ledger: {ledger_status.value}",
                )
                if current is None:
                    return self.lifecycle_store.repair_terminal(repair)
                return self.lifecycle_store.reconcile(
                    request_id,
                    target,
                    updated_at=updated_at,
                    message=repair.message,
                )
