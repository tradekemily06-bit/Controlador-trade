from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.operation_lineage import OperationLineageStore
from core.operation_context_store import OperationContextStore
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
        memory: object | None = None,
        lineage_store: OperationLineageStore | None = None,
        operation_context_store: OperationContextStore | None = None,
    ) -> None:
        if not isinstance(checkpoint_store, RuntimeCheckpointStore):
            raise ValueError("checkpoint_store inválido.")
        if not isinstance(lifecycle_store, ExecutionLifecycleStore):
            raise ValueError("lifecycle_store inválido.")
        if not isinstance(execution_ledger, ExecutionLedger):
            raise ValueError("execution_ledger inválido.")
        self.checkpoint_store = checkpoint_store
        self.lifecycle_store = lifecycle_store
        self.execution_ledger = execution_ledger
        # Kept only as a backward-compatible constructor parameter for the historical P4 recorder; recovery is authoritative from checkpoint/lifecycle/ledger and does not depend on in-process memory.
        self.memory = memory
        self.lineage_store = lineage_store
        self.operation_context_store = operation_context_store

    def assess(self) -> RecoveryAssessment:
        try:
            checkpoint = self.checkpoint_store.load()
            lifecycle = self.lifecycle_store.records()
            ledger_ids = set(self.execution_ledger.records())
        except ValueError as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {exc}")

        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN))

        lifecycle_by_id = {r.request_id: r for r in lifecycle}
        ledger_reserved = set()
        ledger_unknown = set()
        ledger_accepted = set()
        ledger_reconciled_executed = set()
        ledger_reconciled_not_executed = set()
        for request_id in ledger_ids:
            status = self.execution_ledger.status(request_id)
            if status is not None and status.value == "RESERVED":
                ledger_reserved.add(request_id)
            elif status is not None and status.value == "UNKNOWN":
                ledger_unknown.add(request_id)
            elif status is not None and status.value == "ACCEPTED":
                ledger_accepted.add(request_id)
            elif status is not None and status.value == "RECONCILED_EXECUTED":
                ledger_reconciled_executed.add(request_id)
            elif status is not None and status.value == "RECONCILED_NOT_EXECUTED":
                ledger_reconciled_not_executed.add(request_id)

        inconsistent = [
            r.request_id for r in lifecycle
            if (
                (
                    r.state is ExecutionLifecycleState.ACCEPTED
                    and r.request_id not in ledger_accepted
                    and r.request_id not in ledger_reconciled_executed
                )
                or (
                    r.state is ExecutionLifecycleState.REJECTED
                    and r.request_id not in ledger_reconciled_not_executed
                    and r.request_id not in {rid for rid in ledger_ids if self.execution_ledger.status(rid).value == "REJECTED"}
                )
                or (r.state is ExecutionLifecycleState.PENDING and r.request_id not in ledger_reserved and r.request_id not in ledger_unknown)
            )
        ]
        orphan_ledger = sorted(
            request_id for request_id in ledger_ids
            if request_id not in lifecycle_by_id and request_id in (ledger_reserved | ledger_unknown | ledger_accepted)
        )
        identity_inconsistent: list[str] = []
        if self.lineage_store is not None:
            for request_id in sorted(lifecycle_by_id):
                lineage = self.lineage_store.get(request_id)
                if lineage is None:
                    identity_inconsistent.append(request_id)
                    continue
                if self.operation_context_store is not None:
                    context = self.operation_context_store.get(request_id)
                    if context is None or context.decision_id != lineage.decision_id or context.cycle_id != lineage.cycle_id:
                        identity_inconsistent.append(request_id)
                if lifecycle_by_id[request_id].state is ExecutionLifecycleState.ACCEPTED and not lineage.external_id:
                    identity_inconsistent.append(request_id)
            if checkpoint is not None and checkpoint.last_request_id:
                lineage = self.lineage_store.get(checkpoint.last_request_id)
                if lineage is None:
                    identity_inconsistent.append(checkpoint.last_request_id)
                elif checkpoint.last_decision_id not in (None, lineage.decision_id) or checkpoint.last_cycle_id not in (None, lineage.cycle_id):
                    identity_inconsistent.append(checkpoint.last_request_id)
        if identity_inconsistent:
            identity_inconsistent = sorted(set(identity_inconsistent))

        if unknown or pending or inconsistent or orphan_ledger or identity_inconsistent:
            details = []
            if unknown:
                details.append("UNKNOWN requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("Ledger/Lifecycle divergentes requerem reconciliação")
            if orphan_ledger:
                details.append("estado do Ledger sem projeção de Lifecycle requer reconciliação")
            if identity_inconsistent:
                details.append("linhagem/contexto/checkpoint divergentes requerem reconciliação")
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
