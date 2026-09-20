from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p121_external_order_reconciliation import (
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
    ExternalOrderRequestQueryPort,
)
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.models import Signal
from core.kill_switch import KillSwitch
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
        kill_switch: KillSwitch | None = None,
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
        expected_coordination_path = self._locks.global_lock_path
        if kill_switch is None:
            # Even direct low-level construction must fail into the same
            # durable/shared REAL kill-switch boundary as the sanctioned
            # composition function; there must be no in-memory REAL side door.
            kill_switch = KillSwitch(
                ledger.path.parent / "real-kill-switch.json",
                coordination_lock_path=expected_coordination_path,
            )
        elif type(kill_switch) is not KillSwitch:
            raise ValueError("kill_switch inválido.")
        elif getattr(kill_switch, "_path", None) is None:
            raise ValueError("REAL exige kill switch persistente e compartilhado.")
        elif getattr(kill_switch, "_coordination_lock_path", None) != expected_coordination_path:
            raise ValueError(
                "REAL exige kill switch coordenado pela mesma barreira global de execução."
            )
        self._kill_switch = kill_switch

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
        if type(request_id) is not str or not request_id.strip() or request_id != request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido ou não canônico.")
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
        if admission.authorization_id != authorization.authorization_id:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "admissão REAL não pertence à autorização fornecida.")
        if safety.authorization_id != authorization.authorization_id:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "barreira de segurança REAL não pertence à autorização fornecida.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "barreira de segurança REAL não está pronta.",
            )
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id != request_id or request_id != request_id.strip():
            return RealGatewayResult(
                RealGatewayStatus.REJECTED,
                "request_id externo e request.request_id precisam coincidir exatamente e ser canônicos no REAL.",
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
                # Re-read the live kill switch after entering the REAL lock.
                # The safety report is a snapshot; it must never outrank a
                # newer kill-switch activation immediately before dispatch.
                if not self._kill_switch.allows_execution():
                    return RealGatewayResult(
                        RealGatewayStatus.BLOCKED,
                        f"execução REAL bloqueada pelo kill switch: {self._kill_switch.state.reason}",
                    )
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
        if type(request_id) is not str or not request_id.strip() or request_id != request_id.strip():
            raise ValueError("request_id inválido ou não canônico para reconciliação.")
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
        # Recovery is not a dispatch, but it still performs a broker-side
        # external operation. A newly activated REAL kill switch must therefore
        # block reconciliation as well. Because activation uses the same global
        # lock, this check also closes the activation-vs-query race: an
        # activation cannot occur between this check and the broker query.
        if not self._kill_switch.allows_execution():
            raise ValueError(
                f"REAL reconciliation bloqueada pelo kill switch: {self._kill_switch.state.reason}"
            )
        # Check the authoritative durable state before touching the broker.
        # A reconciliation query is not an execution, but it is still an
        # external side effect and must never be used to probe arbitrary IDs.
        status = self._ledger.status(request_id)
        if status not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        query_port = self._gateway.real_query_port(
            broker,
            expected_adapter_id=authorization.adapter_id,
        )
        if query_port is None:
            raise ValueError(
                "adapter REAL autorizado não fornece query_port broker-backed; reconciliação bloqueada."
            )
        lifecycle_status = self._lifecycle_state(request_id)
        consistency = self._check_consistency(status, lifecycle_status, request_id)
        # A persistence failure can leave the authoritative Ledger in
        # RESERVED/UNKNOWN while the Lifecycle projection is missing, PENDING,
        # or UNKNOWN. This is not permission to replay: reconciliation is still
        # gated by a durable external_id and fresh broker-side terminal evidence.
        # Permit only these one-way projection mismatches so reconciliation can
        # close or recreate the projection without ever dispatching again.
        if consistency is not None:
            repairable_projection = (
                status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED)
                and lifecycle_status in (
                    None,
                    ExecutionLifecycleState.PENDING,
                    ExecutionLifecycleState.UNKNOWN,
                )
            )
            if not repairable_projection:
                raise ValueError(consistency.message)

        external_id = self._ledger.external_id(request_id)
        if external_id is None:
            # Crash window: broker accepted after RESERVED/PENDING but the
            # process died before external_id reached the Ledger. Recovery may
            # query only by the same durable request reference that the
            # sanctioned adapter had to send as its client-order-id.
            request_query = self._gateway.real_request_query_port(
                broker,
                expected_adapter_id=authorization.adapter_id,
            )
            if request_query is None:
                raise ValueError(
                    "request_id sem external_id e adapter não oferece consulta broker-backed por referência; reconciliação bloqueada."
                )
            observation = request_query.query_order_by_request_id(request_id)
            if not hasattr(observation, "external_id") or not isinstance(observation.external_id, str) or not observation.external_id.strip():
                raise ValueError("broker retornou observação sem external_id para request_id.")
            if not hasattr(observation, "request_id") or not isinstance(observation.request_id, str) or not observation.request_id.strip():
                raise ValueError("broker retornou observação sem request_id correlacionável.")
            if observation.request_id != request_id:
                raise ValueError("broker retornou observação vinculada a outro request_id.")
            if observation.status not in (
                ExternalOrderStatus.EXECUTED,
                ExternalOrderStatus.NOT_EXECUTED,
                ExternalOrderStatus.PENDING,
                ExternalOrderStatus.UNKNOWN,
            ):
                raise ValueError("broker retornou status externo inválido.")
            if observation.status in (ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN):
                raise ValueError("broker ainda não fornece evidência terminal; reconciliação permanece aberta.")
            observed_id = observation.external_id.strip()
            if observation.status is ExternalOrderStatus.EXECUTED:
                self._ledger.reconcile(
                    request_id,
                    executed=True,
                    external_id=observed_id,
                )
                executed = True
            else:
                self._ledger.reconcile(
                    request_id,
                    executed=False,
                    external_id=observed_id,
                )
                executed = False
            reconciliation = None
        else:
            reconciliation = reconciliation_boundary.reconcile(
                external_id,
                query_port=query_port,
            )
        if reconciliation is not None:
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
