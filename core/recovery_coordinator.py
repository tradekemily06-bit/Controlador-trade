from __future__ import annotations

from dataclasses import dataclass
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

    def assess(self) -> RecoveryAssessment:
        try:
            checkpoint = self.checkpoint_store.load()
            lifecycle = self.lifecycle_store.records()
            ledger_state = self.execution_ledger.snapshot()
            ledger_ids = set(ledger_state)
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        lifecycle_by_id = {record.request_id: record for record in lifecycle}
        lifecycle_pending = {r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING}
        lifecycle_unknown = {r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN}
        checkpoint_orphan: set[str] = set()
        if checkpoint is not None and checkpoint.last_request_id is not None:
            if checkpoint.last_request_id not in lifecycle_by_id and checkpoint.last_request_id not in ledger_ids:
                checkpoint_orphan.add(checkpoint.last_request_id)
        ledger_reserved = {request_id for request_id, state in ledger_state.items() if state is ExecutionLedgerStatus.RESERVED}
        ledger_unknown = {request_id for request_id, state in ledger_state.items() if state is ExecutionLedgerStatus.UNKNOWN}
        pending = tuple(sorted(lifecycle_pending | ledger_reserved))
        unknown = tuple(sorted(lifecycle_unknown | ledger_unknown))

        inconsistent: set[str] = set()
        lifecycle_without_ledger: set[str] = set()
        ledger_without_lifecycle: set[str] = set()
        for request_id, record in lifecycle_by_id.items():
            state = ledger_state.get(request_id)
            if record.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN):
                if state not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                    lifecycle_without_ledger.add(request_id)
            elif record.state is ExecutionLifecycleState.ACCEPTED:
                if state not in (ExecutionLedgerStatus.ACCEPTED, ExecutionLedgerStatus.RECONCILED_EXECUTED):
                    inconsistent.add(request_id)
            elif record.state is ExecutionLifecycleState.REJECTED:
                if state not in (ExecutionLedgerStatus.REJECTED, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED):
                    inconsistent.add(request_id)

        for request_id, state in ledger_state.items():
            if request_id not in lifecycle_by_id and state in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                ledger_without_lifecycle.add(request_id)

        if unknown or pending or inconsistent or lifecycle_without_ledger or ledger_without_lifecycle or checkpoint_orphan:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING/RESERVED requer verificação")
            if inconsistent:
                details.append("ledger/lifecycle com estados incompatíveis")
            if lifecycle_without_ledger:
                details.append("lifecycle sem estado correspondente no ledger")
            if ledger_without_lifecycle:
                details.append("ledger sem lifecycle correspondente")
            if checkpoint_orphan:
                details.append("checkpoint aponta para request_id sem estado persistido")
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
