from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway, _REAL_DISPATCH_CAPABILITY
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class RealGatewayStatus(str):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RealGatewayResult:
    status: str
    message: str
    execution: ExecutionResult | None = None


class RealExecutionGateway:
    """The only REAL dispatch boundary. Broker details stay behind BrokerAdapterGateway."""

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore | None = None, recovery: RecoveryCoordinator | None = None, kill_switch: KillSwitch | None = None, safety_store: OperationalSafetyStore | None = None) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle é obrigatório para execução REAL.")
        if not isinstance(recovery, RecoveryCoordinator):
            raise ValueError("recovery é obrigatório para execução REAL.")
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch é obrigatório para execução REAL.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise ValueError("safety_store inválido.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._recovery = recovery
        self._kill_switch = kill_switch
        self._safety_store = safety_store
        self._processed_request_ids: set[str] = set(ledger.records())

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def _mark_not_dispatched(self, request_id: str, message: str) -> bool:
        """Persist a definitive pre-broker stop without manufacturing UNKNOWN.
        
        A persistence API may raise after its atomic replace already committed.
        Verify the durable authorities before deciding that the terminal stop
        failed; otherwise a harmless post-commit error would unnecessarily turn
        a provably non-dispatched request into UNKNOWN.
        """
        try:
            self._ledger.mark_rejected(request_id)
            durable_status = ExecutionLedgerStatus.REJECTED
        except (OSError, ValueError):
            # A persistence call can fail after committing, or a concurrent
            # recovery worker can have already resolved this request. Re-read
            # the durable authority before declaring the pre-dispatch stop
            # unprovable. Any terminal state proves that this gateway must not
            # dispatch, so it is safe to continue repairing the lifecycle
            # projection rather than manufacturing UNKNOWN.
            try:
                durable_status = self._ledger.status(request_id)
            except (OSError, ValueError):
                return False
            if durable_status not in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                return False

        # The durable ledger remains the authority if a concurrent recovery
        # worker resolved the request while this pre-dispatch stop was being
        # persisted. Never project REJECTED from an already-accepted ledger:
        # doing so would manufacture a cross-store terminal contradiction.
        target_lifecycle = (
            ExecutionLifecycleState.ACCEPTED
            if durable_status in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
            )
            else ExecutionLifecycleState.REJECTED
        )
        record = ExecutionLifecycleRecord(
            request_id,
            target_lifecycle,
            datetime.now(timezone.utc),
            message,
        )
        try:
            current = self._lifecycle.get(request_id)
            if current is not None and current.state in (
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
            ):
                # If the durable ledger is already terminal, a matching
                # terminal lifecycle is sufficient proof that no new broker
                # dispatch may occur. A conflicting terminal projection is
                # never overwritten.
                if (
                    durable_status is ExecutionLedgerStatus.REJECTED
                    and current.state is ExecutionLifecycleState.REJECTED
                ) or (
                    durable_status in (
                        ExecutionLedgerStatus.ACCEPTED,
                        ExecutionLedgerStatus.RECONCILED_EXECUTED,
                    )
                    and current.state is ExecutionLifecycleState.ACCEPTED
                ) or (
                    durable_status is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
                    and current.state is ExecutionLifecycleState.REJECTED
                ):
                    return True
                # A transient PENDING/UNKNOWN projection can still be repaired
                # to the ledger's terminal authority. A conflicting terminal
                # projection must never be overwritten.
                if current.state in (
                    ExecutionLifecycleState.ACCEPTED,
                    ExecutionLifecycleState.REJECTED,
                ):
                    return False
            self._lifecycle.put(record)
        except (OSError, ValueError):
            try:
                current = self._lifecycle.get(request_id)
                if current is None:
                    return False
                if current.state is ExecutionLifecycleState.REJECTED:
                    return True
                if durable_status in (
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ) and current.state is ExecutionLifecycleState.ACCEPTED:
                    return True
                return False
            except (OSError, ValueError):
                return False
        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport) -> RealGatewayResult:
        # Security-boundary inputs must be the concrete contract types.
        if not isinstance(authorization, RealExecutionAuthorization):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inválida.")
        if not isinstance(admission, RealAdmission):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL inválida.")
        if not isinstance(safety, RealSafetyReport):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "relatório de segurança REAL inválido.")
        if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido ou não canônico.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id is not None and request.request_id != request_id:
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "request_id do payload difere do request_id durável.",
            )
        request = replace(request, request_id=request_id)
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        normalized_broker = broker.strip().lower()
        if normalized_broker != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        if normalized_broker != admission.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "broker da requisição difere da admissão REAL.")

        # Check this request's own durable authority before global recovery.
        # After a restart, an UNKNOWN/RESERVED request must remain visibly
        # UNKNOWN (reconciliation required), even when other durable state also
        # makes the runtime globally non-resumable. Never let a global recovery
        # block hide the request's own non-replayable uncertainty.
        try:
            current_status = self._ledger.status(request_id)
        except (OSError, ValueError) as exc:
            # A durable-authority read failure is itself a safety failure.
            # Never continue toward reservation or broker dispatch when the
            # idempotency ledger cannot be read reliably.
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                f"autoridade REAL indisponível; broker não chamado: {exc}",
            )
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                # A crash can occur after ledger admission but before lifecycle
                # publication. Materialize the missing lifecycle uncertainty now,
                # without ever reopening the broker-dispatch path.
                if self._lifecycle.get(request_id) is None:
                    try:
                        self._lifecycle.put(
                            ExecutionLifecycleRecord(
                                request_id,
                                ExecutionLifecycleState.UNKNOWN,
                                datetime.now(timezone.utc),
                                "request_id durável incerto após restart; reconciliação explícita obrigatória.",
                            )
                        )
                    except (OSError, ValueError):
                        pass
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        if self._recovery is not None:
            recovery = self._recovery.assess()
            if recovery.state not in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME):
                return RealGatewayResult(
                    RealGatewayStatus.BLOCKED,
                    f"execução REAL bloqueada pelo estado de recovery: {recovery.state.value}; reconciliação necessária antes de novo envio.",
                )

        if self._lifecycle is not None:
            try:
                existing_lifecycle = self._lifecycle.get(request_id)
            except (OSError, ValueError) as exc:
                # A lifecycle read failure must fail closed before reservation;
                # otherwise a hidden pending/unknown projection could be bypassed.
                return RealGatewayResult(
                    RealGatewayStatus.BLOCKED,
                    f"lifecycle REAL indisponível; broker não chamado: {exc}",
                )
            if existing_lifecycle is not None:
                if existing_lifecycle.state in (
                    ExecutionLifecycleState.PENDING,
                    ExecutionLifecycleState.UNKNOWN,
                ):
                    return RealGatewayResult(
                        RealGatewayStatus.UNKNOWN,
                        "request_id possui lifecycle pendente/incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                    )
                return RealGatewayResult(
                    RealGatewayStatus.BLOCKED,
                    "request_id já possui lifecycle terminal; replay REAL recusado.",
                )
        with self._ledger.real_execution_lock():
            # REAL reservation is already inside the global REAL barrier.
            # The generic Ledger.reserve() remains mode-agnostic and only acquires
            # the per-request identity lock, so DEMO callers do not inherit the
            # REAL global barrier.
            try:
                self._ledger.reserve(request_id)
                self._processed_request_ids.add(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")
    
            # Serialize recovery recheck and lifecycle publication with request-identity
            # discovery. A recovery worker must not resolve RESERVED between the final
            # recovery admission and the publication of PENDING.
            # Recheck after durable reservation but before publishing lifecycle PENDING.
            if self._recovery is not None:
                final_recovery = self._recovery.assess(ignore_request_id=request_id)
                if final_recovery.state not in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME):
                    message = f"execução REAL bloqueada antes do broker pelo estado de recovery: {final_recovery.state.value}."
                    if not self._mark_not_dispatched(request_id, message):
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message} persistência do bloqueio terminal falhou.")
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, message)

            if self._lifecycle is not None:
                try:
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            ExecutionLifecycleState.PENDING,
                            datetime.now(timezone.utc),
                            "REAL reservado; aguardando resultado do broker.",
                        )
                    )
                except (OSError, ValueError) as exc:
                    message = f"não foi possível preparar o lifecycle REAL; broker ainda não foi chamado: {exc}"
                    if not self._mark_not_dispatched(request_id, message):
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message}; persistência do bloqueio terminal falhou.")
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, message)


            # Serialize the final authority check with the broker side effect.
            # Reconciliation for this request takes the same per-request lock, so it
            # cannot resolve RESERVED between the last check and the external call.
            with self._ledger.real_execution_lock():
                # Global REAL admission lock closes the remaining cross-request race:
                # another request becoming UNKNOWN/RESERVED during this final window
                # cannot invalidate the recovery snapshot while this broker call is in
                # flight. Reconciliation/repair workers use the same lock.
                #
                # The recovery check must itself be inside this global barrier. Checking
                # it immediately before acquiring the barrier would still permit another
                # worker to make the runtime unsafe in the gap before the broker call.
                if self._recovery is not None:
                    final_recovery = self._recovery.assess(ignore_request_id=request_id)
                    if final_recovery.state not in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME):
                        message = f"execução REAL bloqueada no limite final pelo estado de recovery: {final_recovery.state.value}."
                        # Recovery may have resolved this exact request while the
                        # gateway was evaluating the snapshot. If the durable
                        # execution authority is already terminal, never attempt to
                        # rewrite it as REJECTED; simply refuse dispatch.
                        try:
                            current_status = self._ledger.status(request_id)
                        except (OSError, ValueError):
                            current_status = None
                        if current_status in (
                            ExecutionLedgerStatus.ACCEPTED,
                            ExecutionLedgerStatus.REJECTED,
                            ExecutionLedgerStatus.RECONCILED_EXECUTED,
                            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                        ):
                            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"{message} autoridade já resolvida como {current_status.value}; broker não chamado.")
                        if self._mark_not_dispatched(request_id, message):
                            return RealGatewayResult(RealGatewayStatus.BLOCKED, message)
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message} persistência do bloqueio terminal falhou.")
                with self._ledger.request_execution_lock(request_id):
                    # Final durable-authority check immediately before the broker side effect.
                    # A reconciliation worker may have completed this request after the
                    # admission snapshot; terminal/UNKNOWN authority must never be replayed.
                    try:
                        final_status = self._ledger.status(request_id)
                    except (OSError, ValueError) as exc:
                        message = f"autoridade REAL indisponível; broker não chamado: {exc}"
                        if self._mark_not_dispatched(request_id, message):
                            return RealGatewayResult(RealGatewayStatus.BLOCKED, message)
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message}; persistência do bloqueio terminal falhou.")
                    if final_status is not ExecutionLedgerStatus.RESERVED:
                        if final_status in (
                            ExecutionLedgerStatus.ACCEPTED,
                            ExecutionLedgerStatus.REJECTED,
                            ExecutionLedgerStatus.RECONCILED_EXECUTED,
                            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                        ):
                            return RealGatewayResult(
                                RealGatewayStatus.BLOCKED,
                                f"execução REAL não enviada: autoridade durável já está {final_status.value}.",
                            )
                        return RealGatewayResult(
                            RealGatewayStatus.UNKNOWN,
                            f"execução REAL não enviada: autoridade durável está {final_status.value if final_status else 'AUSENTE'}.",
                        )
                    try:
                        # The live kill switch is the final mutable safety authority.
                        # Hold its execution window across the external side effect so
                        # an activation racing this boundary cannot interleave between
                        # the last check and the broker call.
                        with self._kill_switch.execution_window():
                            if not self._kill_switch.allows_execution():
                                message = "execução REAL bloqueada pelo kill switch antes do broker."
                                if self._mark_not_dispatched(request_id, message):
                                    return RealGatewayResult(RealGatewayStatus.BLOCKED, message)
                                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message} persistência do bloqueio terminal falhou.")
                            # When durable safety state is available, hold its shared
                            # lock across the final broker side effect. A second
                            # process cannot persist a kill-switch activation while
                            # this window is open, and this process re-reads the
                            # latest durable state instead of trusting a stale
                            # in-memory snapshot.
                            persistent_window = (
                                self._safety_store.kill_switch_execution_window()
                                if self._safety_store is not None
                                else nullcontext(None)
                            )
                            try:
                                with persistent_window as persistent_kill_state:
                                    if persistent_kill_state is not None and persistent_kill_state.enabled:
                                        message = f"execução REAL bloqueada pelo kill switch persistido: {persistent_kill_state.reason}."
                                        if self._mark_not_dispatched(request_id, message):
                                            return RealGatewayResult(RealGatewayStatus.BLOCKED, message)
                                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{message} persistência do bloqueio terminal falhou.")
                                    result = self._gateway.execute_real(
                                        broker, request, capability=_REAL_DISPATCH_CAPABILITY
                                    )
                            except BaseException:
                                # A hard interruption (KeyboardInterrupt/SystemExit)
                                # can happen after the broker side effect. Preserve
                                # the durable pre-broker lifecycle marker so restart
                                # sees RESERVED+PENDING and forces reconciliation;
                                # never attempt a replay here.
                                if self._lifecycle is not None:
                                    try:
                                        current = self._lifecycle.get(request_id)
                                        if current is None:
                                            self._lifecycle.put(
                                                ExecutionLifecycleRecord(
                                                    request_id,
                                                    ExecutionLifecycleState.PENDING,
                                                    datetime.now(timezone.utc),
                                                    "REAL interrompido durante o despacho; resultado requer reconciliação.",
                                                )
                                            )
                                    except (OSError, ValueError):
                                        pass
                                raise
                    except Exception as exc:
                        try:
                            self._ledger.mark_unknown(request_id)
                        except (OSError, ValueError):
                            pass
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc), f"resultado REAL incerto: {type(exc).__name__}: {exc}"))
                            except (OSError, ValueError):
                                pass
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")
                    if result.execution is None:
                        if not result.dispatch_attempted:
                            if self._mark_not_dispatched(request_id, result.message):
                                return RealGatewayResult(RealGatewayStatus.BLOCKED, result.message)
                            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"{result.message}; persistência do bloqueio terminal falhou.")
                        try:
                            self._ledger.mark_unknown(request_id)
                        except (OSError, ValueError):
                            pass
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc), result.message))
                            except (OSError, ValueError):
                                pass
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)
    
                    if not result.execution.accepted:
                        # A negative flag is definitive only when the adapter explicitly
                        # says the outcome is final. Transport/time-out ambiguity must
                        # remain UNKNOWN even when no external_id was returned.
                        if not result.execution.outcome_final:
                            if isinstance(result.execution.external_id, str) and result.execution.external_id.strip():
                                try:
                                    self._ledger.bind_external_id(request_id, result.execution.external_id.strip())
                                except (OSError, ValueError) as exc:
                                    return RealGatewayResult(
                                        RealGatewayStatus.UNKNOWN,
                                        f"resultado negativo ambíguo com external_id, mas persistência falhou: {exc}",
                                        result.execution,
                                    )
                            try:
                                self._ledger.mark_unknown(request_id)
                            except (OSError, ValueError) as exc:
                                return RealGatewayResult(
                                    RealGatewayStatus.UNKNOWN,
                                    f"resultado negativo ambíguo; persistência da incerteza falhou: {exc}",
                                    result.execution,
                                )
                            if self._lifecycle is not None:
                                try:
                                    self._lifecycle.put(
                                        ExecutionLifecycleRecord(
                                            request_id,
                                            ExecutionLifecycleState.UNKNOWN,
                                            datetime.now(timezone.utc),
                                            "resultado negativo não definitivo; resultado externo requer reconciliação.",
                                        )
                                    )
                                except (OSError, ValueError):
                                    pass
                            return RealGatewayResult(
                                RealGatewayStatus.UNKNOWN,
                                "resultado negativo não definitivo; reconciliação explícita necessária.",
                                result.execution,
                            )

                        # A negative result carrying an external reference is also
                        # treated as uncertain: the broker-side identity must be
                        # reconciled before any terminal rejection is projected.
                        if isinstance(result.execution.external_id, str) and result.execution.external_id.strip():
                            try:
                                self._ledger.bind_external_id(request_id, result.execution.external_id.strip())
                                self._ledger.mark_unknown(request_id)
                            except (OSError, ValueError) as exc:
                                return RealGatewayResult(
                                    RealGatewayStatus.UNKNOWN,
                                    f"resposta negativa com external_id, mas persistência da incerteza falhou: {exc}",
                                    result.execution,
                                )
                            if self._lifecycle is not None:
                                try:
                                    self._lifecycle.put(
                                        ExecutionLifecycleRecord(
                                            request_id,
                                            ExecutionLifecycleState.UNKNOWN,
                                            datetime.now(timezone.utc),
                                            "resposta negativa com external_id; resultado externo requer reconciliação.",
                                        )
                                    )
                                except (OSError, ValueError):
                                    pass
                            return RealGatewayResult(
                                RealGatewayStatus.UNKNOWN,
                                "resposta negativa com external_id; reconciliação explícita necessária.",
                                result.execution,
                            )
    
                        try:
                            self._ledger.mark_rejected(request_id)
                        except (OSError, ValueError) as exc:
                            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, datetime.now(timezone.utc), result.execution.message))
                            except (OSError, ValueError) as exc:
                                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada no ledger, mas lifecycle não foi persistido: {exc}", result.execution)
                        return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)
    
                    # An accepted REAL result without a durable broker/exchange reference is
                    # ambiguous: the external order may exist but cannot be safely reconciled.
                    if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
                        try:
                            self._ledger.mark_unknown(request_id)
                        except (OSError, ValueError) as exc:
                            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(
                                    ExecutionLifecycleRecord(
                                        request_id,
                                        ExecutionLifecycleState.UNKNOWN,
                                        datetime.now(timezone.utc),
                                        "aceite REAL sem external_id; identidade externa não é reconciliável com segurança.",
                                    )
                                )
                            except (OSError, ValueError):
                                pass
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)
    
                    try:
                        self._ledger.bind_external_id(request_id, result.execution.external_id.strip())
                        self._ledger.mark_accepted(request_id)
                    except (OSError, ValueError) as exc:
                        # The broker has already accepted the order. Any persistence
                        # failure therefore remains uncertain; never leave the lifecycle
                        # claiming that the request is merely pre-broker PENDING.
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(
                                    ExecutionLifecycleRecord(
                                        request_id,
                                        ExecutionLifecycleState.UNKNOWN,
                                        datetime.now(timezone.utc),
                                        f"ordem REAL aceita, mas persistência do ledger falhou: {exc}",
                                    )
                                )
                            except (OSError, ValueError):
                                pass
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
                    if self._lifecycle is not None:
                        try:
                            self._lifecycle.put(
                                ExecutionLifecycleRecord(
                                    request_id,
                                    ExecutionLifecycleState.ACCEPTED,
                                    datetime.now(timezone.utc),
                                    result.execution.message,
                                )
                            )
                        except (OSError, ValueError) as exc:
                            # Ledger is already terminal and externally identified. The
                            # lifecycle must never remain PENDING after broker acceptance:
                            # persist UNKNOWN as the explicit cross-store uncertainty
                            # marker, then let recovery repair/reconcile it later.
                            try:
                                self._lifecycle.put(
                                    ExecutionLifecycleRecord(
                                        request_id,
                                        ExecutionLifecycleState.UNKNOWN,
                                        datetime.now(timezone.utc),
                                        f"ordem REAL aceita no ledger, mas lifecycle não foi persistido: {exc}",
                                    )
                                )
                            except (OSError, ValueError):
                                pass
                            return RealGatewayResult(
                                RealGatewayStatus.UNKNOWN,
                                f"ordem REAL aceita no ledger, mas lifecycle não foi persistido: {exc}",
                                result.execution,
                            )
                    return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)
    

    def reconcile_unknown(
        self,
        request_id: str,
        *,
        observation: ExternalOrderObservation,
    ) -> None:
        """Apply broker-observed evidence; never manufacture broker state locally.

        The caller must provide an observation obtained from a read-only broker
        reconciliation path. A bare executed boolean plus an arbitrary
        external_id is intentionally rejected because that combination would be
        a durable-state side door: local code could otherwise manufacture
        ACCEPTED/REJECTED REAL authority without broker evidence.
        """
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("reconciliação REAL exige observação externa verificável.")

        if self._ledger.status(request_id) not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        if self._lifecycle is None:
            raise ValueError("reconciliação REAL exige lifecycle durável.")

        lifecycle_record = self._lifecycle.get(request_id)
        if lifecycle_record is None:
            raise ValueError("reconciliação REAL exige lifecycle durável para o request_id.")

        if lifecycle_record.state not in (
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.UNKNOWN,
        ):
            raise ValueError("lifecycle do request_id não está em estado incerto reconciliável.")

        if not isinstance(observation.external_id, str) or not observation.external_id.strip():
            raise ValueError("external_id durável é obrigatório para reconciliação externa segura.")

        ExecutionReconciliationCoordinator(
            ledger=self._ledger,
            lifecycle=self._lifecycle,
        ).reconcile(
            request_id,
            observation.external_id.strip(),
            observation,
        )
