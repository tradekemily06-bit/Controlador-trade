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
            ledger_ids = set(self.execution_ledger.records())
            ledger_states = {
                request_id: self.execution_ledger.status(request_id)
                for request_id in ledger_ids
            }
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = tuple(sorted(
            {
                r.request_id
                for r in lifecycle
                if r.state is ExecutionLifecycleState.UNKNOWN
            }
            | {
                request_id
                for request_id, state in ledger_states.items()
                if state in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED)
            }
        ))

        lifecycle_by_id = {record.request_id: record for record in lifecycle}
        inconsistent = []
        if checkpoint is not None and checkpoint.last_request_id is not None:
            checkpoint_request_id = checkpoint.last_request_id
            if checkpoint_request_id not in ledger_ids or checkpoint_request_id not in lifecycle_by_id:
                inconsistent.append(checkpoint_request_id)
        for request_id in sorted(ledger_ids | set(lifecycle_by_id)):
            ledger_state = ledger_states.get(request_id)
            lifecycle_record = lifecycle_by_id.get(request_id)
            lifecycle_state = lifecycle_record.state if lifecycle_record is not None else None
            if ledger_state is None:
                inconsistent.append(request_id)
                continue
            if lifecycle_state is None:
                inconsistent.append(request_id)
                continue
            allowed_pairs = {
                ExecutionLifecycleState.PENDING: {ExecutionLedgerStatus.RESERVED},
                ExecutionLifecycleState.UNKNOWN: {ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED},
                ExecutionLifecycleState.ACCEPTED: {
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
                },
                ExecutionLifecycleState.REJECTED: {
                    ExecutionLedgerStatus.REJECTED,
                    ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                },
            }
            if ledger_state not in allowed_pairs[lifecycle_state]:
                inconsistent.append(request_id)
                continue
            if ledger_state in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                identity = self.execution_ledger.record_for(request_id)
                if identity is None or identity.external_id is None:
                    inconsistent.append(request_id)

        if unknown or pending or inconsistent:
            details = []
            if unknown:
                details.append("UNKNOWN/RESERVED requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("Ledger/Lifecycle/checkpoint/identidade externa divergentes ou incompletos requerem reconciliação")
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
