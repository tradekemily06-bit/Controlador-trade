from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore


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

    def __init__(
        self,
        *,
        checkpoint_store: RuntimeCheckpointStore,
        lifecycle_store: ExecutionLifecycleStore,
        execution_ledger: ExecutionLedger,
        memory: OperationMemory,
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

    def repair_terminal_lifecycle_projection(self, request_id: str) -> None:
        """Explicitly repair Lifecycle from a terminal Ledger record; never contacts or replays the broker."""
        status = self.execution_ledger.status(request_id)
        if status is ExecutionLedgerStatus.ACCEPTED:
            state = ExecutionLifecycleState.ACCEPTED
        elif status is ExecutionLedgerStatus.REJECTED:
            state = ExecutionLifecycleState.REJECTED
        elif status is ExecutionLedgerStatus.RECONCILED_EXECUTED:
            state = ExecutionLifecycleState.ACCEPTED
        elif status is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED:
            state = ExecutionLifecycleState.REJECTED
        else:
            raise ValueError("somente estados terminais do Ledger podem reparar a projeção.")

        self.lifecycle_store.project_terminal(
            request_id,
            state,
            updated_at=datetime.now(timezone.utc),
            message="projeção Lifecycle reparada a partir do Ledger terminal; nenhuma ordem enviada",
        )

    def assess(self) -> RecoveryAssessment:
        try:
            checkpoint = self.checkpoint_store.load()
            lifecycle = self.lifecycle_store.records()
            ledger_ids = set(self.execution_ledger.records())
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN))

        lifecycle_ids = {r.request_id for r in lifecycle}
        ledger_statuses = {
            request_id: self.execution_ledger.status(request_id)
            for request_id in ledger_ids
        }
        missing_external_reference = [
            request_id
            for request_id, status in ledger_statuses.items()
            if status in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            )
            and self.execution_ledger.external_reference_required(request_id)
            and self.execution_ledger.external_id(request_id) is None
        ]
        inconsistent = [
            r.request_id
            for r in lifecycle
            if (
                (r.state is ExecutionLifecycleState.ACCEPTED and ledger_statuses.get(r.request_id) not in (
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ))
                or (r.state is ExecutionLifecycleState.REJECTED and ledger_statuses.get(r.request_id) not in (
                    ExecutionLedgerStatus.REJECTED,
                    ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                ))
                or (r.state is ExecutionLifecycleState.PENDING and ledger_statuses.get(r.request_id) not in (
                    ExecutionLedgerStatus.RESERVED,
                    ExecutionLedgerStatus.UNKNOWN,
                ))
                or (r.state is ExecutionLifecycleState.UNKNOWN and ledger_statuses.get(r.request_id) not in (
                    ExecutionLedgerStatus.UNKNOWN,
                    ExecutionLedgerStatus.RESERVED,
                ))
            )
        ]
        orphaned_ledger_ids = sorted(ledger_ids - lifecycle_ids)
        if unknown or pending or inconsistent or orphaned_ledger_ids or missing_external_reference:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("Ledger e Lifecycle estão inconsistentes; reconciliação obrigatória")
            if orphaned_ledger_ids:
                details.append("ledger sem lifecycle requer reconciliação")
            if missing_external_reference:
                details.append("estado terminal sem external_id durável; reconciliação/auditoria obrigatória")
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
