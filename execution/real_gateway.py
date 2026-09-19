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

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, release: RealReleaseClosure) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not isinstance(release, RealReleaseClosure) or not release.released:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "release REAL não está formalmente fechado.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request_id, request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
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

        current_status = self._ledger.status(request_id)
        if current_status is not None:
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

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

        if ledger_status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
            desired_ledger,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        now = datetime.now(timezone.utc)
        if lifecycle is None:
            # Crash window: ledger exists but lifecycle was never persisted.
            # Reconciliation may reconstruct only an UNKNOWN marker; it never
            # treats the missing record as permission to dispatch.
            lifecycle = ExecutionLifecycleRecord(
                request_id,
                ExecutionLifecycleState.UNKNOWN,
                now,
                "estado reconstruído durante reconciliação explícita; nenhum replay permitido.",
            )
            self._lifecycle.put(lifecycle)

        if lifecycle.state not in (ExecutionLifecycleState.UNKNOWN, desired_lifecycle):
            raise ValueError("ciclo de execução não está em estado reconciliável.")

        # Each side is made idempotent so a crash between these two durable
        # stores can be retried safely without resubmitting the external order.
        if ledger_status is not desired_ledger:
            self._ledger.reconcile(request_id, executed=executed)

        if lifecycle.state is not desired_lifecycle:
            self._lifecycle.reconcile(
                request_id,
                desired_lifecycle,
                updated_at=now,
                message="reconciliação REAL explícita.",
            )
