from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.p119_release_closure import RealReleaseClosure
from execution.adapter_gateway import BrokerAdapterGateway, _REAL_DISPATCH_CAPABILITY
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.execution_coordination import ExecutionCoordinationLock
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

    def __init__(
        self,
        adapter_gateway: BrokerAdapterGateway,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
    ) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle é obrigatório para execução REAL.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._coordination = ExecutionCoordinationLock(ledger.path)

    @staticmethod
    def _valid_request(request_id: str, request: ExecutionRequest) -> bool:
        if not isinstance(request_id, str) or not request_id.strip():
            return False
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if request.request_id is not None and (
            not isinstance(request.request_id, str)
            or request.request_id.strip() != request_id.strip()
        ):
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def _recovery_safe(self) -> bool:
        """Block new REAL dispatch when any durable execution state needs repair."""
        try:
            lifecycle = self._lifecycle.records()
            ledger_ids = self._ledger.records()
            ledger_states = {request_id: self._ledger.status(request_id) for request_id in ledger_ids}
        except (OSError, ValueError):
            return False

        lifecycle_by_id = {record.request_id: record for record in lifecycle}
        if any(record.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN) for record in lifecycle):
            return False

        if set(lifecycle_by_id) != set(ledger_states):
            return False

        for request_id, status in ledger_states.items():
            record = lifecycle_by_id[request_id]
            if status is ExecutionLedgerStatus.ACCEPTED and record.state is not ExecutionLifecycleState.ACCEPTED:
                return False
            if status is ExecutionLedgerStatus.REJECTED and record.state is not ExecutionLifecycleState.REJECTED:
                return False
            if status is ExecutionLedgerStatus.RECONCILED_EXECUTED and record.state is not ExecutionLifecycleState.ACCEPTED:
                return False
            if status is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED and record.state is not ExecutionLifecycleState.REJECTED:
                return False
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                return False

        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, release: RealReleaseClosure) -> RealGatewayResult:
        # Recovery assessment, reservation and the external side effect share
        # one process/host coordination boundary. This prevents a concurrent
        # recovery or second REAL request from observing a transient safe state.
        with self._coordination.acquire():
            return self._execute_locked(
                broker=broker,
                request_id=request_id,
                request=request,
                authorization=authorization,
                admission=admission,
                safety=safety,
                release=release,
            )

    def _execute_locked(self, *, broker: str, request_id: str, request: ExecutionRequest,
                        authorization: RealExecutionAuthorization, admission: RealAdmission,
                        safety: RealSafetyReport, release: RealReleaseClosure) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if type(release) is not RealReleaseClosure or not release.released:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "release REAL não está formalmente fechado.")
        if type(authorization) is not RealExecutionAuthorization or not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if type(admission) is not RealAdmission or not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if type(safety) is not RealSafetyReport or not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request_id, request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        # A request already recorded in an uncertain state must report UNKNOWN
        # for that same request_id. Only genuinely new requests are blocked by
        # unrelated recovery debt elsewhere in the execution stores.
        current_status = self._ledger.status(request_id)
        if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
            )
        if current_status is not None:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")
        if not self._recovery_safe():
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "estado de execução exige reconciliação; novo despacho REAL bloqueado.",
            )
        if request.request_id is None:
            # Bind the canonical ledger identity into the broker-facing request.
            request = replace(request, request_id=request_id)
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        registered_adapter_id = self._gateway.adapter_id(broker)
        if not isinstance(registered_adapter_id, str) or not registered_adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "adapter REAL sem identidade registrada.")
        if registered_adapter_id.strip() != authorization.adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "adapter da requisição difere da autorização.")

        try:
            self._ledger.reserve(request_id)
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id,
                    ExecutionLifecycleState.PENDING,
                    datetime.now(timezone.utc),
                    "execução REAL reservada; despacho externo ainda não confirmado.",
                )
            )
        except (OSError, ValueError) as exc:
            # If the ledger reservation succeeded but its lifecycle marker did not,
            # never proceed to an external side effect. Marking UNKNOWN is the
            # safest durable outcome; recovery will detect any cross-store gap.
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"reserva REAL persistida, mas ciclo de execução não pôde ser persistido: {exc}",
            )

        try:
            result = self._gateway.execute_real(
                broker, request, capability=_REAL_DISPATCH_CAPABILITY
            )
        except Exception as exc:
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
                        f"resultado REAL incerto: {type(exc).__name__}: {exc}",
                    )
                )
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
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
                        result.message,
                    )
                )
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.REJECTED,
                        datetime.now(timezone.utc),
                        result.execution.message,
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id,
                        ExecutionLifecycleState.UNKNOWN,
                        datetime.now(timezone.utc),
                        "aceite REAL sem external_id; reconciliação explícita necessária.",
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.mark_accepted(request_id)
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id,
                    ExecutionLifecycleState.ACCEPTED,
                    datetime.now(timezone.utc),
                    result.execution.message,
                )
            )
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        """Explicitly reconcile an uncertain request without any replay."""
        with self._coordination.acquire():
            self._reconcile_unknown_locked(request_id, executed=executed)

    def _reconcile_unknown_locked(self, request_id: str, *, executed: bool) -> None:
        ledger_status = self._ledger.status(request_id)
        lifecycle = self._lifecycle.get(request_id)
        desired_ledger = (
            ExecutionLedgerStatus.RECONCILED_EXECUTED
            if executed
            else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
        )
        desired_lifecycle = (
            ExecutionLifecycleState.ACCEPTED
            if executed
            else ExecutionLifecycleState.REJECTED
        )

        terminal_status = (
            ExecutionLedgerStatus.ACCEPTED
            if executed
            else ExecutionLedgerStatus.REJECTED
        )
        if ledger_status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
            terminal_status,
            desired_ledger,
        ):
            raise ValueError("request_id não está em estado reconciliável.")

        now = datetime.now(timezone.utc)
        if lifecycle is None:
            # Ledger-only crash window: the external outcome is being reconciled
            # explicitly. Create the terminal Lifecycle record only after the
            # Ledger reconciliation below; never invent a PENDING/UNKNOWN record
            # through the normal put() transition path.
            lifecycle_missing = True
        else:
            lifecycle_missing = False

        if lifecycle is not None and lifecycle.state not in (
            ExecutionLifecycleState.UNKNOWN,
            ExecutionLifecycleState.PENDING,
            desired_lifecycle,
        ):
            raise ValueError("ciclo de execução não está em estado reconciliável.")

        # A terminal Ledger state is authoritative evidence that the external
        # side-effect was already classified. A crash can occur after the
        # Ledger commit but before the Lifecycle commit, leaving PENDING on the
        # second store. In that case synchronization is safe and must never
        # redispatch the broker request.
        if ledger_status is not desired_ledger:
            self._ledger.reconcile(request_id, executed=executed)
            # The transition above is now durable. Use the post-reconciliation
            # state when deciding whether the Lifecycle PENDING crash window can
            # be closed; using the stale pre-repair state would reject a valid
            # terminal-Ledger/PENDING-Lifecycle repair.
            ledger_status = desired_ledger

        if lifecycle_missing:
            self._lifecycle.reconcile_missing(
                request_id,
                desired_lifecycle,
                updated_at=now,
                message="ciclo criado durante reconciliação de um Ledger sem Lifecycle; nenhum replay permitido.",
            )
            return

        if lifecycle.state is not desired_lifecycle:
            if lifecycle.state is ExecutionLifecycleState.PENDING and ledger_status is desired_ledger:
                self._lifecycle.reconcile_pending(
                    request_id,
                    desired_lifecycle,
                    updated_at=now,
                    message="ciclo sincronizado após janela de crash entre Ledger e Lifecycle.",
                )
            elif lifecycle.state is ExecutionLifecycleState.UNKNOWN:
                self._lifecycle.reconcile(
                    request_id,
                    desired_lifecycle,
                    updated_at=now,
                    message="reconciliação REAL explícita.",
                )
            else:
                raise ValueError("Ledger e Lifecycle não formam uma combinação reconciliável.")
