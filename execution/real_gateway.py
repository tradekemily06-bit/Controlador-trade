from __future__ import annotations

from dataclasses import dataclass
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
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
        self._processed_request_ids: set[str] = set(ledger.records())

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
        # Global lock -> request lock -> durable persistence is enforced by
        # RealExecutionLocks. No broker call happens before RESERVED is durable.
        current_status = self._ledger.status(request_id)
        lifecycle_status = self._lifecycle_state(request_id)

        consistency = self._check_consistency(
            current_status,
            lifecycle_status,
            request_id,
        )
        if consistency is not None:
            return consistency

        if current_status is not None:
            self._processed_request_ids.add(request_id)
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
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                f"não foi possível reservar request_id com segurança: {exc}",
            )

        try:
            result = self._gateway.execute(broker, request)
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
                self._ledger.mark_rejected(
                    request_id,
                    external_id=execution.external_id,
                )
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

        # The broker accepted. Persist the broker reference before attempting
        # the terminal ACCEPTED transition so a crash cannot erase the
        # reconciliation handle.
        external_id = execution.external_id
        if not isinstance(external_id, str) or not external_id.strip():
            self._mark_unknown(
                request_id,
                "aceite REAL sem external_id; reconciliação explícita necessária.",
            )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                "aceite REAL sem external_id; reconciliação explícita necessária.",
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
            # Ledger is authoritative and already contains external_id. The
            # lifecycle projection cannot promote/downgrade execution locally.
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
        executed: bool,
        external_id: str | None = None,
    ) -> None:
        status = self._ledger.status(request_id)
        if status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")
        with self._locks.acquire(request_id):
            self._ledger.reconcile(
                request_id,
                executed=executed,
                external_id=external_id,
            )
            state = (
                ExecutionLifecycleState.ACCEPTED
                if executed
                else ExecutionLifecycleState.REJECTED
            )
            self._set_lifecycle(request_id, state, "reconciliação explícita")

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
                updated_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
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
