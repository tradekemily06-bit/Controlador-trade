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

        lifecycle_by_id = {r.request_id: r for r in lifecycle}
        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN))

        inconsistent = [
            r.request_id
            for r in lifecycle
            if r.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED)
            and r.request_id not in ledger_ids
        ]
        ledger_only = []
        ledger_mismatch = []
        for request_id in sorted(ledger_ids):
            status = self.execution_ledger.status(request_id)
            record = lifecycle_by_id.get(request_id)
            if record is None:
                if status in (
                    ExecutionLedgerStatus.RESERVED,
                    ExecutionLedgerStatus.UNKNOWN,
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.REJECTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
                    ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                ):
                    ledger_only.append(request_id)
                continue
            expected_states = {
                ExecutionLedgerStatus.ACCEPTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.REJECTED: ExecutionLifecycleState.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED: ExecutionLifecycleState.REJECTED,
            }
            expected = expected_states.get(status)
            if expected is not None and record.state is not expected:
                ledger_mismatch.append(request_id)
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                ledger_mismatch.append(request_id)

        if unknown or pending or inconsistent or ledger_only or ledger_mismatch:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("estado terminal do lifecycle sem ledger requer reconciliação")
            if ledger_only:
                details.append("estado do ledger sem lifecycle correspondente requer reconciliação")
            if ledger_mismatch:
                details.append("ledger e lifecycle estão divergentes")
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
