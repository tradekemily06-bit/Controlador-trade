from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
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
            ledger_ids = set(self.execution_ledger.records())
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        lifecycle_pending = {r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING}
        lifecycle_unknown = {r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN}
        ledger_reserved = {request_id for request_id in ledger_ids if self.execution_ledger.status(request_id) is ExecutionLedgerStatus.RESERVED}
        ledger_unknown = {request_id for request_id in ledger_ids if self.execution_ledger.status(request_id) is ExecutionLedgerStatus.UNKNOWN}
        pending = tuple(sorted(lifecycle_pending | ledger_reserved))
        unknown = tuple(sorted(lifecycle_unknown | ledger_unknown))

        inconsistent = [r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.ACCEPTED and r.request_id not in ledger_ids]
        lifecycle_without_ledger = [r.request_id for r in lifecycle if r.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN) and r.request_id not in ledger_ids]
        if unknown or pending or inconsistent or lifecycle_without_ledger:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("ACCEPTED sem ledger requer reconciliação")
            if ledger_reserved:
                details.append("RESERVED no ledger requer reconciliação")
            if ledger_unknown:
                details.append("UNKNOWN no ledger requer reconciliação")
            if lifecycle_without_ledger:
                details.append("lifecycle sem ledger requer reconciliação")
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
