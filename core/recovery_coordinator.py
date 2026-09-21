from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from core.operation_memory import OperationMemory
from core.runtime_checkpoint import RuntimeCheckpoint,RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger,ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState,ExecutionLifecycleStore
from execution.execution_coordination import ExecutionCoordinationLock

class RecoveryState(str,Enum):
    FRESH="FRESH"; SAFE_TO_RESUME="SAFE_TO_RESUME"; REQUIRES_RECONCILIATION="REQUIRES_RECONCILIATION"; INVALID="INVALID"

@dataclass(frozen=True)
class RecoveryAssessment:
    state:RecoveryState
    checkpoint:RuntimeCheckpoint|None
    pending_request_ids:tuple[str,...]
    unknown_request_ids:tuple[str,...]
    message:str
    inconsistent_request_ids:tuple[str,...]=()
    @property
    def can_resume(self): return self.state in (RecoveryState.FRESH,RecoveryState.SAFE_TO_RESUME)

class RecoveryCoordinator:
    """Restart assessor; any cross-store execution ambiguity blocks resume."""
    def __init__(self,*,checkpoint_store,lifecycle_store,execution_ledger,memory):
        if not isinstance(checkpoint_store,RuntimeCheckpointStore): raise ValueError("checkpoint_store inválido.")
        if not isinstance(lifecycle_store,ExecutionLifecycleStore): raise ValueError("lifecycle_store inválido.")
        if not isinstance(execution_ledger,ExecutionLedger): raise ValueError("execution_ledger inválido.")
        if not isinstance(memory,OperationMemory): raise ValueError("memory inválida.")
        self.checkpoint_store=checkpoint_store; self.lifecycle_store=lifecycle_store; self.execution_ledger=execution_ledger; self.memory=memory
        self._coordination=ExecutionCoordinationLock(execution_ledger.path)

    def assess(self):
        with self._coordination.acquire():
            return self._assess_locked()

    def _assess_locked(self):
        try:
            checkpoint=self.checkpoint_store.load()
            lifecycle=self.lifecycle_store.records()
            ids=self.execution_ledger.records()
            ledger={rid:self.execution_ledger.status(rid) for rid in ids}
        except (OSError,ValueError) as exc:
            return RecoveryAssessment(RecoveryState.INVALID,None,(),(),f"estado persistido inválido: {exc}")
        by_id={r.request_id:r for r in lifecycle}
        pending=tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown=tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN))
        bad=set()
        for rid,r in by_id.items():
            ls=ledger.get(rid)
            if r.state is ExecutionLifecycleState.PENDING and ls not in (None,ExecutionLedgerStatus.RESERVED): bad.add(rid)
            elif r.state is ExecutionLifecycleState.UNKNOWN and ls not in (None,ExecutionLedgerStatus.RESERVED,ExecutionLedgerStatus.UNKNOWN,ExecutionLedgerStatus.RECONCILED_EXECUTED,ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED): bad.add(rid)
            elif r.state is ExecutionLifecycleState.ACCEPTED and ls not in (ExecutionLedgerStatus.ACCEPTED,ExecutionLedgerStatus.RECONCILED_EXECUTED): bad.add(rid)
            elif r.state is ExecutionLifecycleState.REJECTED and ls is not ExecutionLedgerStatus.REJECTED: bad.add(rid)
        for rid,ls in ledger.items():
            if rid not in by_id:
                bad.add(rid)
                continue
            rs=by_id[rid].state
            if ls in (ExecutionLedgerStatus.ACCEPTED,ExecutionLedgerStatus.RECONCILED_EXECUTED,ExecutionLedgerStatus.REJECTED,ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED) and rs in (ExecutionLifecycleState.PENDING,ExecutionLifecycleState.UNKNOWN):
                bad.add(rid)
            if ls in (ExecutionLedgerStatus.ACCEPTED,ExecutionLedgerStatus.RECONCILED_EXECUTED) and not self.execution_ledger.external_id(rid):
                bad.add(rid)
        if pending or unknown or bad:
            details=[]
            if pending: details.append("PENDING requer verificação")
            if unknown: details.append("UNKNOWN requer reconciliação")
            if bad: details.append("divergência Ledger/Lifecycle requer reconciliação")
            return RecoveryAssessment(RecoveryState.REQUIRES_RECONCILIATION,checkpoint,pending,unknown,"; ".join(details),tuple(sorted(bad)))
        state=RecoveryState.FRESH if checkpoint is None else RecoveryState.SAFE_TO_RESUME
        return RecoveryAssessment(state,checkpoint,(),(),"nenhum estado pendente; retomada sem replay automático" if checkpoint else "nenhum checkpoint; sessão pode iniciar com segurança",())
