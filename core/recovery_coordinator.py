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
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        lifecycle_unknown = {r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN}
        ledger_uncertain = {
            request_id
            for request_id in ledger_ids
            if self.execution_ledger.status(request_id)
            in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
        }
        unknown = tuple(sorted(lifecycle_unknown | ledger_uncertain))

        ledger_statuses = {
            request_id: self.execution_ledger.status(request_id)
            for request_id in ledger_ids
        }
        lifecycle_ids = {record.request_id for record in lifecycle}
        inconsistent = []

        # Validate both directions of the durable state machine. A restart
        # must not silently trust a terminal state that exists in only one
        # store, nor accept contradictory lifecycle/ledger states.
        allowed_ledger_states = {
            ExecutionLifecycleState.PENDING: {
                None,
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            },
            ExecutionLifecycleState.UNKNOWN: {
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            },
            ExecutionLifecycleState.ACCEPTED: {
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
            },
            ExecutionLifecycleState.REJECTED: {
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            },
        }
        for record in lifecycle:
            ledger_status = ledger_statuses.get(record.request_id)
            if ledger_status not in allowed_ledger_states[record.state]:
                inconsistent.append(record.request_id)

        # The inverse direction matters: a terminal ledger record without a
        # lifecycle record means the durable stores have lost correlation.
        for request_id, ledger_status in ledger_statuses.items():
            if request_id not in lifecycle_ids and ledger_status not in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            ):
                inconsistent.append(request_id)

        inconsistent = sorted(set(inconsistent))
        if unknown or pending or inconsistent:
            details = []
            if unknown:
                details.append("UNKNOWN/RESERVED requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("Lifecycle/Ledger inconsistente requer reconciliação")
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
