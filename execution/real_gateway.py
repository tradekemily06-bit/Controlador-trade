from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p121_external_order_reconciliation import (
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.models import Signal
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
        if type(adapter_gateway) is not BrokerAdapterGateway:
            raise ValueError("adapter_gateway inválido.")
        if type(ledger) is not ExecutionLedger:
            raise ValueError("ledger é obrigatório para execução REAL.")
        if lifecycle is not None and type(lifecycle) is not ExecutionLifecycleStore:
            raise ValueError("lifecycle inválido.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._locks = RealExecutionLocks(ledger.path)

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if type(request) is not ExecutionRequest:
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if (
            not isinstance(request.amount, (int, float))
            or isinstance(request.amount, bool)
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
        if type(authorization) is not RealExecutionAuthorization:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "autorização REAL inválida.")
        if type(admission) is not RealAdmission:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "admissão REAL inválida.")
        if type(safety) is not RealSafetyReport:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL inválida.")
        if (
            authorization.explicitly_enabled is not True
            or authorization.real_execution_allowed is not True
        ):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        for field_name in ("authorization_id", "audit_id", "broker_id", "adapter_id"):
            field_value = getattr(authorization, field_name, None)
            if type(field_value) is not str or not field_value.strip():
                return RealGatewayResult(
                    RealGatewayStatus.REJECTED,
                    f"campo {field_name} da autorização REAL é inválido.",
                )
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "barreira de segurança REAL não está pronta.",
            )
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id != request_id:
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "request_id externo e request.request_id precisam coincidir no REAL.",
            )
        if type(broker) is not str or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if type(admission.broker_id) is not str or admission.broker_id.strip().lower() != broker.strip().lower():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "broker da admissão difere do broker da execução REAL.",
            )
        if type(admission.audit_id) is not str or admission.audit_id.strip().lower() != authorization.audit_id.strip().lower():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "auditoria da admissão difere da autorização REAL.",
            )
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "broker da requisição difere da autorização.",
            )
        adapter_id = self._gateway.real_adapter_id(broker)
        if adapter_id is None:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "adapter REAL sem identidade explícita; execução bloqueada.",
            )
        if adapter_id.strip().lower() != authorization.adapter_id.strip().lower():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "adapter da execução difere da autorização REAL.",
            )
        try:
            with self._locks.acquire(request_id):
                # Pin the REAL adapter only after entering the same lock that
                # protects reservation and dispatch. This removes the
                # authorization-to-capability TOCTOU window.
                capability = self._gateway._real_dispatch_capability(
                    broker,
                    expected_adapter_id=authorization.adapter_id,
                    request_id=request_id,
                    authorization_id=authorization.authorization_id,
                )
                if capability is None:
                    return RealGatewayResult(
                        RealGatewayStatus.BLOCKED,
                        "adapter REAL autorizado não pôde ser fixado.",
                    )
                return self._execute_locked(
                    broker=broker,
                    request_id=request_id,
                    request=request,
                    capability=capability,
                    authorization_id=authorization.authorization_id,
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
        capability,
        authorization_id: str,
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
            result = self._gateway._execute_real(
                broker, request, capability=capability, request_id=request_id, authorization_id=authorization_id
            )
        except Exception as exc:
            message = f"resultado REAL incerto: {type(exc).__name__}: {exc}"
            persistence_warning = self._mark_unknown(request_id, message)
            if persistence_warning:
                message = f"{message}; persistência de estado incerto também falhou: {persistence_warning}"
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, message)

        if result.execution is None:
            persistence_warning = self._mark_unknown(request_id, result.message)
            message = result.message
            if persistence_warning:
                message = f"{message}; persistência de estado incerto também falhou: {persistence_warning}"
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, message)

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
            message = "aceite REAL sem external_id; reconciliação por referência do broker é impossível."
            persistence_warning = self._mark_unknown(request_id, message)
            if persistence_warning:
                message = f"{message}; persistência de estado incerto também falhou: {persistence_warning}"
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, message, execution)

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
        broker: str,
        authorization: RealExecutionAuthorization,
        reconciliation_boundary: ExternalOrderReconciliationBoundary,
    ) -> None:
        """Reconcile only from a broker-side read, never from local state.

        The broker reference must already be durable in the Ledger. A request
        with no external_id cannot be safely resolved through an external-id
        lookup and therefore remains UNKNOWN until a broker-neutral
        request-id/client-order-id query port exists.
        """
        if type(reconciliation_boundary) is not ExternalOrderReconciliationBoundary:
            raise ValueError("boundary de reconciliação inválida.")
        if type(authorization) is not RealExecutionAuthorization:
            raise ValueError("autorização REAL inválida.")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido para reconciliação.")
        if (
            authorization.explicitly_enabled is not True
            or authorization.real_execution_allowed is not True
        ):
            raise ValueError("autorização REAL inativa.")
        for field_name in ("authorization_id", "audit_id", "broker_id", "adapter_id"):
            field_value = getattr(authorization, field_name, None)
            if type(field_value) is not str or not field_value.strip():
                raise ValueError(f"campo {field_name} da autorização REAL é inválido.")
        if not isinstance(broker, str) or not broker.strip():
            raise ValueError("broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            raise ValueError("broker da reconciliação difere da autorização.")
        try:
            lock_context = self._locks.acquire(request_id)
            with lock_context:
                return self._reconcile_unknown_locked(
                    request_id=request_id,
                    broker=broker,
                    authorization=authorization,
                    reconciliation_boundary=reconciliation_boundary,
                )
        except RealExecutionLockError as exc:
            raise ValueError(f"REAL bloqueado: lock de reconciliação indisponível: {exc}") from exc

    def _reconcile_unknown_locked(
        self,
        request_id: str,
        *,
        broker: str,
        authorization: RealExecutionAuthorization,
        reconciliation_boundary: ExternalOrderReconciliationBoundary,
    ) -> None:
        # The caller already holds the global -> request REAL lock.
        query_port = self._gateway.real_query_port(
            broker,
            expected_adapter_id=authorization.adapter_id,
        )
        if query_port is None:
            raise ValueError(
                "adapter REAL autorizado não fornece query_port broker-backed; reconciliação bloqueada."
            )

        status = self._ledger.status(request_id)
        if status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")
        lifecycle_status = self._lifecycle_state(request_id)
        consistency = self._check_consistency(status, lifecycle_status, request_id)
        # A failed UNKNOWN projection can leave Lifecycle=PENDING while the
        # authoritative Ledger is already UNKNOWN. This is not permission to
        # replay; it is precisely a reconciliation-repair case. Permit only
        # this one-way mismatch so broker-side evidence can close both stores.
        if consistency is not None:
            if not (
                status is ExecutionLedgerStatus.UNKNOWN
                and lifecycle_status in (None, ExecutionLifecycleState.PENDING)
            ):
                raise ValueError(consistency.message)

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
            raise ValueError(
                "broker ainda não fornece estado terminal; reconciliação permanece aberta."
            )

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
            try:
                updated_at = datetime.now(timezone.utc)
                current = self._lifecycle.get(request_id)
                if current is None:
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id,
                            state,
                            updated_at,
                            "projeção Lifecycle criada durante reconciliação externa",
                        )
                    )
                else:
                    self._lifecycle.reconcile(
                        request_id,
                        state,
                        updated_at=updated_at,
                        message="reconciliação externa consultada no broker",
                    )
            except (OSError, ValueError) as exc:
                # Ledger is authoritative. If the projection write fails after
                # durable reconciliation, never reopen or replay the order;
                # surface a repairable projection failure instead.
                raise ValueError(
                    f"Ledger reconciliado, mas projeção Lifecycle falhou: {exc}"
                ) from exc

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
            record = ExecutionLifecycleRecord(
                request_id=request_id,
                state=state,
                updated_at=datetime.now(timezone.utc),
                message="projeção Lifecycle reparada a partir do Ledger autoritativo",
            )
            current = self._lifecycle.get(request_id)
            if current is None or current.state is state:
                self._lifecycle.put(record)
            else:
                self._lifecycle.reconcile(
                    request_id,
                    state,
                    updated_at=record.updated_at,
                    message=record.message,
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

    def _mark_unknown(self, request_id: str, message: str) -> str | None:
        failures: list[str] = []
        try:
            self._ledger.mark_unknown(request_id)
        except (OSError, ValueError) as exc:
            failures.append(f"Ledger: {exc}")
        if self._lifecycle is not None:
            try:
                self._set_lifecycle(request_id, ExecutionLifecycleState.UNKNOWN, message)
            except (OSError, ValueError) as exc:
                failures.append(f"Lifecycle: {exc}")
        return "; ".join(failures) if failures else None

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
