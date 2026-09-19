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
        except (OSError, ValueError) as exc:
            return RecoveryAssessment(
                RecoveryState.INVALID,
                None,
                (),
                (),
                f"estado persistido inválido: {exc}",
            )

        try:
            lifecycle_by_id = {record.request_id: record for record in lifecycle}
            ledger_by_id = {
                request_id: self.execution_ledger.entry(request_id)
                for request_id in ledger_ids
            }

            pending: set[str] = set()
            unknown: set[str] = set()
            inconsistent: set[str] = set()

            expected = {
                "RESERVED": ExecutionLifecycleState.PENDING,
                "ACCEPTED": ExecutionLifecycleState.ACCEPTED,
                "REJECTED": ExecutionLifecycleState.REJECTED,
                "UNKNOWN": ExecutionLifecycleState.UNKNOWN,
                "RECONCILED_EXECUTED": ExecutionLifecycleState.ACCEPTED,
                "RECONCILED_NOT_EXECUTED": ExecutionLifecycleState.REJECTED,
            }

            all_ids = set(ledger_by_id) | set(lifecycle_by_id)
            for request_id in all_ids:
                entry = ledger_by_id.get(request_id)
                lifecycle_record = lifecycle_by_id.get(request_id)

                if entry is None or lifecycle_record is None:
                    inconsistent.add(request_id)
                    if entry is not None and entry.status.value in ("RESERVED", "UNKNOWN"):
                        unknown.add(request_id)
                    if lifecycle_record is not None and lifecycle_record.state is ExecutionLifecycleState.UNKNOWN:
                        unknown.add(request_id)
                    if lifecycle_record is not None and lifecycle_record.state is ExecutionLifecycleState.PENDING:
                        pending.add(request_id)
                    continue

                if entry.status.value in ("RESERVED", "UNKNOWN"):
                    unknown.add(request_id)
                if lifecycle_record.state is ExecutionLifecycleState.PENDING:
                    pending.add(request_id)
                if lifecycle_record.state is ExecutionLifecycleState.UNKNOWN:
                    unknown.add(request_id)

                if expected.get(entry.status.value) is not lifecycle_record.state:
                    inconsistent.add(request_id)

            if unknown or pending or inconsistent:
                details = []
                if unknown:
                    details.append("UNKNOWN/RESERVED requer reconciliação")
                if pending:
                    details.append("PENDING requer verificação")
                if inconsistent:
                    details.append("Ledger × Lifecycle inconsistente")
                return RecoveryAssessment(
                    RecoveryState.REQUIRES_RECONCILIATION,
                    checkpoint,
                    tuple(sorted(pending)),
                    tuple(sorted(unknown)),
                    "; ".join(details),
                )

            state = RecoveryState.FRESH if checkpoint is None else RecoveryState.SAFE_TO_RESUME
            message = (
                "nenhum estado pendente; retomada segura sem replay automático"
                if checkpoint
                else "nenhum checkpoint; sessão pode iniciar com segurança"
            )
            return RecoveryAssessment(
                state,
                checkpoint,
                (),
                (),
                message,
            )
        except (OSError, ValueError) as exc:
            return RecoveryAssessment(
                RecoveryState.INVALID,
                None,
                (),
                (),
                f"não foi possível avaliar o estado persistido com segurança: {exc}",
            )
