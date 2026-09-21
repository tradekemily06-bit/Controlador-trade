from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from core.file_lock import exclusive_file_lock


class RecoveryState(str, Enum):
    FRESH = "FRESH"
    SAFE_TO_RESUME = "SAFE_TO_RESUME"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"
    SESSION_MISMATCH = "SESSION_MISMATCH"
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
        # Recovery must share the same cross-process dispatch lock used by
        # execution gateways. Otherwise it can observe the Ledger/Lifecycle
        # pair between two durable mutations and falsely conclude the state is
        # safe to resume.
        self._coordination_lock_path = execution_ledger.path.with_name(
            f".{execution_ledger.path.name}.dispatch.lock"
        )

    def repair_terminal_lifecycle(
        self,
        request_id: str,
        *,
        updated_at,
        message: str = "internal persistence repair from authoritative ledger",
    ):
        """Repair only a durable Ledger/Lifecycle persistence divergence.

        This never queries or calls a broker. The Ledger must already contain
        a terminal state, while Lifecycle may be missing or PENDING. Terminal
        mismatches and UNKNOWN are deliberately not auto-repaired.
        """
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(updated_at, datetime):
            raise ValueError("updated_at inválido.")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message inválida.")

        with exclusive_file_lock(self._coordination_lock_path):
            ledger_states = self.execution_ledger.snapshot()
            ledger_status = ledger_states.get(request_id)
            target = {
                ExecutionLedgerStatus.ACCEPTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.REJECTED: ExecutionLifecycleState.REJECTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED: ExecutionLifecycleState.REJECTED,
            }.get(ledger_status)
            if target is None:
                raise ValueError("reparo interno exige estado terminal autoritativo no Ledger.")

            current = self.lifecycle_store.get(request_id)
            if current is not None:
                if current.state is target:
                    return current
                if current.state is not ExecutionLifecycleState.PENDING:
                    raise ValueError("divergência terminal não pode ser reparada automaticamente.")
            record = ExecutionLifecycleRecord(
                request_id=request_id.strip(),
                state=target,
                updated_at=updated_at,
                message=message.strip(),
            )
            self.lifecycle_store.put(record)
            return record

    def assess(self, *, session_id: str | None = None) -> RecoveryAssessment:
        if session_id is not None and (not isinstance(session_id, str) or not session_id.strip()):
            raise ValueError("session_id inválido.")

        try:
            with exclusive_file_lock(self._coordination_lock_path):
                checkpoint = self.checkpoint_store.load()
                lifecycle = self.lifecycle_store.records()
                ledger_states = self.execution_ledger.snapshot()
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            return RecoveryAssessment(RecoveryState.INVALID, None, (), (), f"estado persistido inválido: {type(exc).__name__}")

        lifecycle_by_id = {record.request_id: record for record in lifecycle}
        pending = tuple(sorted(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.PENDING))
        unknown = set(r.request_id for r in lifecycle if r.state is ExecutionLifecycleState.UNKNOWN)

        # A durable RESERVED/UNKNOWN ledger state is itself enough to block
        # automatic resume, even when the lifecycle file is missing or stale.
        uncertain_ledger = {
            request_id
            for request_id, status in ledger_states.items()
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
        }
        unknown.update(uncertain_ledger)

        inconsistent: list[str] = []
        for record in lifecycle:
            ledger_status = ledger_states.get(record.request_id)
            if record.state is ExecutionLifecycleState.ACCEPTED and ledger_status not in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ):
                inconsistent.append(record.request_id)
            elif record.state is ExecutionLifecycleState.REJECTED and ledger_status not in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                inconsistent.append(record.request_id)
            elif record.state is ExecutionLifecycleState.UNKNOWN and ledger_status not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                inconsistent.append(record.request_id)

        # The inverse direction matters too: a terminal ledger entry without
        # a lifecycle record means the two durable sources no longer describe
        # the same execution history. Resume is therefore unsafe until the
        # discrepancy is explicitly investigated/reconciled.
        terminal_ledger_states = {
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.REJECTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        }
        for request_id, ledger_status in ledger_states.items():
            if ledger_status in terminal_ledger_states and request_id not in lifecycle_by_id:
                inconsistent.append(request_id)

        inconsistent = sorted(set(inconsistent))

        checkpoint_orphan = None
        if checkpoint is not None and checkpoint.last_request_id:
            request_id = checkpoint.last_request_id
            if request_id not in lifecycle_by_id and request_id not in ledger_states:
                checkpoint_orphan = request_id

        if unknown or pending or inconsistent or checkpoint_orphan:
            details = []
            if unknown:
                details.append("UNKNOWN/estado incerto durável requer reconciliação")
            if pending:
                details.append("PENDING requer verificação")
            if inconsistent:
                details.append("lifecycle e ledger divergem; reconciliação obrigatória")
            if checkpoint_orphan:
                details.append("checkpoint aponta para request_id ausente no lifecycle e ledger; requer reconciliação")
            return RecoveryAssessment(
                RecoveryState.REQUIRES_RECONCILIATION,
                checkpoint,
                pending,
                tuple(sorted(unknown)),
                "; ".join(details),
            )

        if checkpoint is not None and session_id is not None and checkpoint.session_id != session_id:
            return RecoveryAssessment(
                RecoveryState.SESSION_MISMATCH,
                checkpoint,
                (),
                (),
                "checkpoint pertence a outra sessão; retomada automática bloqueada",
            )

        state = RecoveryState.FRESH if checkpoint is None else RecoveryState.SAFE_TO_RESUME
        message = "nenhum estado pendente; retomada segura sem replay automático" if checkpoint else "nenhum checkpoint; sessão pode iniciar com segurança"
        return RecoveryAssessment(state, checkpoint, (), (), message)
