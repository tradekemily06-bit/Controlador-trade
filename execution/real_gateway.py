from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p121_external_order_reconciliation import (
    ExternalOrderQueryPort,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway, _REAL_DISPATCH_CAPABILITY
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_execution_locks import RealExecutionLockError, RealExecutionLocks


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
    """The only REAL dispatch boundary.

    Adapter dispatch is reachable here only through BrokerAdapterGateway.
    The ledger is the durable authority; lifecycle is a consistency/audit
    projection and never promotes UNKNOWN locally.
    """

    def __init__(
        self,
        adapter_gateway: BrokerAdapterGateway,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore | None = None,
    ) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if lifecycle is not None and not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._locks = RealExecutionLocks(ledger.path)

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if (
            not isinstance(request.amount, (int, float))
            or not math.isfinite(request.amount)
            or request.amount <= 0
        ):
            return False
        if (
            not isinstance(request.duration_seconds, int)
            or isinstance(request.duration_seconds, bool)
            or request.duration_seconds <= 0
        ):
            return False
        return True

    def execute(
        self,
        *,
        broker: str,
        request_id: str,
        request: ExecutionRequest,
        authorization: RealExecutionAuthorization,
        admission: RealAdmission,
        safety: RealSafetyReport,
    ) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "barreira de segurança REAL não está pronta.",
            )
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "broker da requisição difere da autorização.",
            )

        try:
            with self._locks.acquire(request_id):
                return self._execute_locked(
                    broker=broker,
                    request_id=request_id,
                    request=request,
                )
        except RealExecutionLockError as exc:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                f"REAL bloqueado: lock de execução indisponível: {exc}",
            )

    def _execute_locked(
        self,
        *,
        broker: str,
        request_id: str,
        request: ExecutionRequest,
    ) -> RealGatewayResult:
        current_status = self._ledger.status(request_id)
        lifecycle_status = self._lifecycle_state(request_id)

        consistency = self._check_consistency(current_status, lifecycle_status, request_id)
        if consistency is not None:
            return consistency

        if current_status is not None:
            if current_status in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "request_id já processado; replay REAL recusado.",
            )

        try:
            self._ledger.reserve(request_id)
            self._set_lifecycle(
                request_id,
                ExecutionLifecycleState.PENDING,
                "REAL reservado antes do dispatch",
            )
        except (OSError, ValueError) as exc:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                f"não foi possível reservar request_id com segurança: {exc}",
            )

        try:
            result = self._gateway.execute_real(
                broker, request, capability=_REAL_DISPATCH_CAPABILITY
            )
        except Exception as exc:
            self._mark_unknown(
                request_id,
                f"resultado REAL incerto: {type(exc).__name__}: {exc}",
            )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"resultado REAL incerto: {type(exc).__name__}: {exc}",
            )

        if result.execution is None:
            self._mark_unknown(request_id, result.message)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        execution = result.execution

        if not execution.accepted:
            try:
                self._ledger.mark_rejected(request_id, external_id=execution.external_id)
                self._set_lifecycle(
                    request_id,
                    ExecutionLifecycleState.REJECTED,
                    execution.message,
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"ordem rejeitada, mas persistência do estado falhou: {exc}",
                    execution,
                )
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                execution.message,
                execution,
            )

        external_id = execution.external_id
        if not isinstance(external_id, str) or not external_id.strip():
            self._mark_unknown(
                request_id,
                "aceite REAL sem external_id; reconciliação por referência do broker é impossível.",
            )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                "aceite REAL sem external_id; reconciliação por referência do broker é impossível.",
                execution,
            )

        try:
            self._ledger.attach_external_id(request_id, external_id)
            self._ledger.mark_accepted(request_id, external_id=external_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"ordem REAL aceita, mas persistência do ledger falhou: {exc}",
                execution,
            )

        try:
            self._set_lifecycle(
                request_id,
                ExecutionLifecycleState.ACCEPTED,
                execution.message,
            )
        except (OSError, ValueError) as exc:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"ordem REAL aceita e ledger persistido, mas lifecycle falhou: {exc}",
                execution,
            )

        return RealGatewayResult(
            RealGatewayStatus.ADMITTED,
            execution.message,
            execution,
        )

    def reconcile_unknown(
        self,
        request_id: str,
        *,
        reconciliation_boundary: ExternalOrderReconciliationBoundary,
        query_port: ExternalOrderQueryPort,
    ) -> None:
        """Reconcile only from a broker-side read, never from local state.

        The broker reference must already be durable in the Ledger. A request
        with no external_id cannot be safely resolved through an external-id
        lookup and therefore remains UNKNOWN until a broker-neutral
        request-id/client-order-id query port exists.
        """
        if not isinstance(reconciliation_boundary, ExternalOrderReconciliationBoundary):
            raise ValueError("boundary de reconciliação inválida.")
        if not isinstance(query_port, ExternalOrderQueryPort):
            raise ValueError("query_port de reconciliação inválido.")

        with self._locks.acquire(request_id):
            status = self._ledger.status(request_id)
            if status not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")

            external_id = self._ledger.external_id(request_id)
            if external_id is None:
                raise ValueError(
                    "request_id não possui external_id durável; reconciliação por external_id bloqueada."
                )

            reconciliation = reconciliation_boundary.reconcile(
                external_id,
                query_port=query_port,
            )
            if not reconciliation.reconciled:
                raise ValueError("broker ainda não fornece estado terminal; reconciliação permanece aberta.")

            executed = reconciliation.status is ExternalOrderStatus.EXECUTED
            self._ledger.reconcile(
                request_id,
                executed=executed,
                external_id=reconciliation.external_id,
            )
            if self._lifecycle is not None:
                state = (
                    ExecutionLifecycleState.ACCEPTED
                    if executed
                    else ExecutionLifecycleState.REJECTED
                )
                self._lifecycle.reconcile(
                    request_id,
                    state,
                    updated_at=datetime.now(timezone.utc),
                    message="reconciliação externa consultada no broker",
                )

    def repair_lifecycle_projection(self, request_id: str) -> None:
        with self._locks.acquire(request_id):
            entry = self._ledger.entry(request_id)
            if entry is None:
                raise ValueError("request_id não existe no Ledger.")
            if self._lifecycle is None:
                return
            state_by_ledger = {
                ExecutionLedgerStatus.ACCEPTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.REJECTED: ExecutionLifecycleState.REJECTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED: ExecutionLifecycleState.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED: ExecutionLifecycleState.REJECTED,
            }
            state = state_by_ledger.get(entry.status)
            if state is None:
                raise ValueError("Ledger ainda não possui estado terminal reparável.")
            self._lifecycle.reconcile(
                request_id,
                state,
                updated_at=datetime.now(timezone.utc),
                message="projeção Lifecycle reparada a partir do Ledger autoritativo",
            )

    def _lifecycle_state(self, request_id: str) -> ExecutionLifecycleState | None:
        if self._lifecycle is None:
            return None
        record = self._lifecycle.get(request_id)
        return record.state if record else None

    def _set_lifecycle(
        self,
        request_id: str,
        state: ExecutionLifecycleState,
        message: str,
    ) -> None:
        if self._lifecycle is None:
            return
        self._lifecycle.put(
            ExecutionLifecycleRecord(
                request_id=request_id,
                state=state,
                updated_at=datetime.now(timezone.utc),
                message=message,
            )
        )

    def _mark_unknown(self, request_id: str, message: str) -> None:
        try:
            self._ledger.mark_unknown(request_id)
        except (OSError, ValueError):
            pass
        if self._lifecycle is not None:
            try:
                self._set_lifecycle(request_id, ExecutionLifecycleState.UNKNOWN, message)
            except (OSError, ValueError):
                pass

    def _check_consistency(
        self,
        ledger_status: ExecutionLedgerStatus | None,
        lifecycle_status: ExecutionLifecycleState | None,
        request_id: str,
    ) -> RealGatewayResult | None:
        if self._lifecycle is None:
            return None

        expected = {
            ExecutionLedgerStatus.RESERVED: ExecutionLifecycleState.PENDING,
            ExecutionLedgerStatus.ACCEPTED: ExecutionLifecycleState.ACCEPTED,
            ExecutionLedgerStatus.REJECTED: ExecutionLifecycleState.REJECTED,
            ExecutionLedgerStatus.UNKNOWN: ExecutionLifecycleState.UNKNOWN,
            ExecutionLedgerStatus.RECONCILED_EXECUTED: ExecutionLifecycleState.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED: ExecutionLifecycleState.REJECTED,
        }
        if ledger_status is None and lifecycle_status is None:
            return None
        if ledger_status is None or lifecycle_status is None:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"Ledger × Lifecycle inconsistente para {request_id}; reconciliação obrigatória.",
            )
        if expected.get(ledger_status) is not lifecycle_status:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"Ledger × Lifecycle inconsistente para {request_id}; replay bloqueado.",
            )
        return None
