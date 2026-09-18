from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p3_execution_reconciliation import ExecutionReconciliationCoordinator
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.kill_switch import KillSwitch
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore | None = None, recovery: RecoveryCoordinator | None = None, kill_switch: KillSwitch | None = None) -> None:
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
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._recovery = recovery
        self._kill_switch = kill_switch
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
        current_status = self._ledger.status(request_id)
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
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
            existing_lifecycle = self._lifecycle.get(request_id)
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
        try:
            self._ledger.reserve(request_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        # Serialize recovery recheck and lifecycle publication with request-identity
        # discovery. A recovery worker must not resolve RESERVED between the final
        # recovery admission and the publication of PENDING.
        with self._ledger.request_execution_lock(request_id):
            # Recheck after durable reservation but before publishing lifecycle PENDING.
            if self._recovery is not None:
                final_recovery = self._recovery.assess(ignore_request_id=request_id)
                if final_recovery.state not in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME):
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        pass
                    if self._lifecycle is not None:
                        try:
                            self._lifecycle.put(
                                ExecutionLifecycleRecord(
                                    request_id,
                                    ExecutionLifecycleState.UNKNOWN,
                                    datetime.now(timezone.utc),
                                    f"recovery mudou antes do executor REAL: {final_recovery.state.value}",
                                )
                            )
                        except (OSError, ValueError):
                            pass
                    return RealGatewayResult(
                        RealGatewayStatus.BLOCKED,
                        f"execução REAL bloqueada imediatamente antes do executor: {final_recovery.state.value}; estado marcado como UNKNOWN.",
                    )
    
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
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        pass
                    try:
                        self._lifecycle.put(
                            ExecutionLifecycleRecord(
                                request_id,
                                ExecutionLifecycleState.UNKNOWN,
                                datetime.now(timezone.utc),
                                f"não foi possível preparar o lifecycle REAL; estado incerto: {exc}",
                            )
                        ) if self._lifecycle is not None else None
                    except (OSError, ValueError):
                        pass
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível preparar o lifecycle REAL; estado incerto bloqueado: {exc}")
    
    
        # Serialize the final authority check with the broker side effect.
        # Reconciliation for this request takes the same per-request lock, so it
        # cannot resolve RESERVED between the last check and the external call.
        with self._ledger.request_execution_lock(request_id):
            # Final durable-authority check immediately before the broker side effect.
            # A reconciliation worker may have completed this request after the
            # admission snapshot; terminal/UNKNOWN authority must never be replayed.
            try:
                final_status = self._ledger.status(request_id)
            except (OSError, ValueError) as exc:
                try:
                    self._ledger.mark_unknown(request_id)
                except (OSError, ValueError):
                    pass
                if self._lifecycle is not None:
                    try:
                        self._lifecycle.put(
                            ExecutionLifecycleRecord(
                                request_id,
                                ExecutionLifecycleState.UNKNOWN,
                                datetime.now(timezone.utc),
                                f"não foi possível confirmar a autoridade REAL antes do broker: {exc}",
                            )
                        )
                    except (OSError, ValueError):
                        pass
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"autoridade REAL indisponível; broker não chamado: {exc}",
                )
            if final_status is not ExecutionLedgerStatus.RESERVED:
                if final_status in (
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
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
                        try:
                            self._ledger.mark_unknown(request_id)
                        except (OSError, ValueError):
                            pass
                        if self._lifecycle is not None:
                            try:
                                self._lifecycle.put(
                                    ExecutionLifecycleRecord(
                                        request_id,
                                        ExecutionLifecycleState.UNKNOWN,
                                        datetime.now(timezone.utc),
                                        "kill switch ativado antes da fronteira final do broker.",
                                    )
                                )
                            except (OSError, ValueError):
                                pass
                        return RealGatewayResult(
                            RealGatewayStatus.BLOCKED,
                            "execução REAL bloqueada pelo kill switch antes do broker.",
                        )
                    result = self._gateway.execute(broker, request)
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
                # A negative flag is not sufficient to prove that no external
                # order exists. Some broker APIs can return an external reference
                # alongside a rejection/ambiguous response. In that contradictory
                # case, persist identity + UNKNOWN and reconcile instead of
                # manufacturing a definitive REJECTED terminal state.
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
        executed: bool,
        external_id: str | None = None,
    ) -> None:
        """Explicitly reconcile uncertainty without ever resubmitting the order.

        Reconciliation must cross durable authorities and carry externally
        observed identity. A bare boolean cannot prove broker state, so the
        old ledger-only reconciliation path is intentionally fail-closed.
        """
        if self._ledger.status(request_id) not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        # lifecycle and recovery are mandatory REAL authorities; this branch
        # is retained as a defensive assertion for future refactors.
        if self._lifecycle is None:
            raise ValueError("reconciliação REAL exige lifecycle durável.")

        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError(
                "reconciliação com lifecycle exige external_id durável; "
                "use o serviço de reconciliação externa para consultar o broker."
            )

        observation = ExternalOrderObservation(
            external_id=external_id.strip(),
            status=(
                ExternalOrderStatus.EXECUTED
                if executed
                else ExternalOrderStatus.NOT_EXECUTED
            ),
            message="reconciliação explícita solicitada pelo gateway",
        )
        ExecutionReconciliationCoordinator(
            ledger=self._ledger,
            lifecycle=self._lifecycle,
        ).reconcile(
            request_id,
            external_id.strip(),
            observation,
        )
