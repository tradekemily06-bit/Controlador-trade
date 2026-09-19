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
    inconsistent_request_ids: tuple[str, ...] = ()

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
            ledger_states = {
                request_id: self.execution_ledger.status(request_id)
                for request_id in self.execution_ledger.records()
            }
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN))
        inconsistent: set[str] = set()

        for record in lifecycle:
            ledger_status = ledger_states.get(record.request_id)
            if record.state is ExecutionLifecycleState.ACCEPTED and ledger_status is not ExecutionLedgerStatus.ACCEPTED:
                inconsistent.add(record.request_id)
            elif record.state is ExecutionLifecycleState.PENDING and ledger_status is not None:
                inconsistent.add(record.request_id)
            elif record.state is ExecutionLifecycleState.UNKNOWN and ledger_status not in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            ):
                inconsistent.add(record.request_id)

        for request_id, ledger_status in ledger_states.items():
            if ledger_status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                record = next((item for item in lifecycle if item.request_id == request_id), None)
                if record is None or record.state is not ExecutionLifecycleState.UNKNOWN:
                    inconsistent.add(request_id)

        if unknown or pending or inconsistent:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("Ledger/Lifecycle divergentes requerem reconciliação")
            return RecoveryAssessment(
                RecoveryState.REQUIRES_RECONCILIATION,
                checkpoint,
                pending,
                unknown,
                "; ".join(details),
                tuple(sorted(inconsistent)),
            )

        state = RecoveryState.FRESH if checkpoint is None else RecoveryState.SAFE_TO_RESUME
        message = "nenhum estado pendente; retomada segura sem replay automático" if checkpoint else "nenhum checkpoint; sessão pode iniciar com segurança"
        return RecoveryAssessment(state, checkpoint, (), (), message)
