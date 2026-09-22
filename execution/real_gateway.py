from __future__ import annotations

from dataclasses import dataclass, replace
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.kill_switch import KillSwitch
from core.models import Signal
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from datetime import datetime, timezone
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from execution.execution_coordination import ExecutionCoordinationLock


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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore, kill_switch: KillSwitch) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle é obrigatório para execução REAL.")
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch é obrigatório para execução REAL.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._kill_switch = kill_switch
        self._processed_request_ids: set[str] = set(ledger.records())
        self._coordination = ExecutionCoordinationLock(ledger.path)

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
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return False
        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport) -> RealGatewayResult:
        with self._coordination.acquire():
            return self._execute_locked(broker=broker, request_id=request_id, request=request, authorization=authorization, admission=admission, safety=safety)

    def _execute_locked(self, *, broker: str, request_id: str, request: ExecutionRequest,
                        authorization: RealExecutionAuthorization, admission: RealAdmission,
                        safety: RealSafetyReport) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        # Re-check the live kill switch immediately before reserving/dispatching;
        # a previously evaluated safety snapshot may be stale.
        if not self._kill_switch.allows_execution():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativo no momento da execução REAL.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id is None:
            request = replace(request, request_id=request_id)
        elif request.request_id != request_id:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id externo difere do request_id interno.")
        if admission.broker_id.strip().lower() != broker.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da admissão difere do broker da execução.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        try:
            registered_adapter_id = self._gateway.adapter_id(broker)
        except Exception as exc:
            return RealGatewayResult(RealGatewayStatus.REJECTED, f"adapter REAL não registrado: {exc}")
        if registered_adapter_id.strip().lower() != authorization.adapter_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "adapter da autorização difere do adapter efetivamente registrado.")

        current_status = self._ledger.status(request_id)
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        try:
            self._ledger.reserve(request_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        event_time = datetime.now(timezone.utc)
        try:
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id, ExecutionLifecycleState.PENDING, event_time, "execução REAL iniciada"
                )
            )
        except (OSError, ValueError) as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"reserva REAL persistida, mas Lifecycle PENDING falhou; reconciliação necessária: {exc}",
            )

        # Hold the in-process kill-switch guard across the final check and
        # external dispatch. This prevents another thread from activating or
        # deactivating the switch between the check and the broker call.
        with self._kill_switch.execution_guard():
            if not self._kill_switch.allows_execution():
                try:
                    self._ledger.mark_rejected(request_id)
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id, ExecutionLifecycleState.REJECTED, event_time,
                            "kill switch ativado antes do dispatch REAL",
                        )
                    )
                except (OSError, ValueError) as exc:
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"kill switch bloqueou o dispatch, mas a rejeição não pôde ser persistida: {exc}")
                return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativado antes do dispatch REAL.")

            try:
                result = self._gateway.execute(broker, request)
            except Exception as exc:
                try:
                    self._mark_uncertain(request_id, event_time, f"resultado REAL incerto: {type(exc).__name__}: {exc}")
                except (OSError, ValueError) as persist_exc:
                    return RealGatewayResult(
                        RealGatewayStatus.UNKNOWN,
                        f"resultado REAL incerto e persistência do estado incompleta; recuperação necessária: {persist_exc}",
                    )
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            if not result.dispatch_started:
                try:
                    self._ledger.mark_rejected(request_id)
                    self._lifecycle.put(
                        ExecutionLifecycleRecord(
                            request_id, ExecutionLifecycleState.REJECTED, event_time, result.message
                        )
                    )
                except (OSError, ValueError) as exc:
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"execução não iniciada, mas persistência da rejeição falhou: {exc}")
                return RealGatewayResult(RealGatewayStatus.REJECTED, result.message)
            try:
                self._mark_uncertain(request_id, event_time, result.message)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"resultado REAL pós-dispatch incerto e persistência incompleta; recuperação necessária: {exc}",
                )
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if result.execution.ambiguous:
            if result.execution.external_id:
                try:
                    self._ledger.bind_external_id(request_id, result.execution.external_id)
                except (OSError, ValueError) as exc:
                    return RealGatewayResult(
                        RealGatewayStatus.UNKNOWN,
                        f"resultado REAL ambíguo e external_id não foi persistido: {exc}",
                        result.execution,
                    )
            try:
                self._mark_uncertain(request_id, event_time, result.execution.message)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    f"resultado REAL ambíguo e persistência do UNKNOWN falhou: {exc}",
                    result.execution,
                )
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"resultado REAL ambíguo; reconciliação explícita necessária: {result.execution.message}",
                result.execution,
            )

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
                self._lifecycle.put(
                    ExecutionLifecycleRecord(
                        request_id, ExecutionLifecycleState.REJECTED, event_time, result.execution.message
                    )
                )
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._mark_uncertain(request_id, event_time, "aceite REAL sem external_id")
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.bind_external_id(request_id, result.execution.external_id)
            self._ledger.mark_accepted(request_id)
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id, ExecutionLifecycleState.ACCEPTED, event_time, result.execution.message
                )
            )
        except (OSError, ValueError) as exc:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"ordem REAL aceita e Ledger persistido, mas Lifecycle não foi persistido; recuperação necessária: {exc}",
                result.execution,
            )
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def _mark_uncertain(self, request_id: str, timestamp: datetime, message: str) -> None:
        self._ledger.mark_unknown(request_id)
        self._lifecycle.put(
            ExecutionLifecycleRecord(
                request_id, ExecutionLifecycleState.UNKNOWN, timestamp, message
            )
        )

    def recover_lifecycle_from_durable_acceptance(self, request_id: str) -> None:
        with self._coordination.acquire():
            self._recover_lifecycle_from_durable_acceptance_locked(request_id)

    def _recover_lifecycle_from_durable_acceptance_locked(self, request_id: str) -> None:
        """Repair only local Lifecycle evidence from an already durable acceptance.

        This path never dispatches, never changes Ledger state, and never invents
        a broker result. It exists for the crash window after Ledger ACCEPTED but
        before Lifecycle ACCEPTED (or when the Lifecycle file was lost).
        """
        current = self._ledger.status(request_id)
        if current not in (
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
        ):
            raise ValueError("Ledger não contém aceite durável recuperável.")
        external_id = self._ledger.external_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("aceite durável sem external_id; recuperação bloqueada.")

        lifecycle = self._lifecycle.get(request_id)
        if lifecycle is not None and lifecycle.state is ExecutionLifecycleState.ACCEPTED:
            return
        if lifecycle is not None and lifecycle.state not in (
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.UNKNOWN,
        ):
            raise ValueError("Lifecycle não está em estado recuperável.")

        message = f"Lifecycle recuperado a partir do aceite durável do Ledger; external_id={external_id.strip()}"
        if lifecycle is None:
            self._lifecycle.reconcile_missing(
                request_id,
                ExecutionLifecycleState.ACCEPTED,
                updated_at=datetime.now(timezone.utc),
                message=message,
            )
        else:
            self._lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.ACCEPTED,
                updated_at=datetime.now(timezone.utc),
                message=message,
            )

    def recover_lifecycle_from_durable_rejection(self, request_id: str) -> None:
        with self._coordination.acquire():
            self._recover_lifecycle_from_durable_rejection_locked(request_id)

    def _recover_lifecycle_from_durable_rejection_locked(self, request_id: str) -> None:
        """Repair Lifecycle from a durable local rejection without querying or dispatching externally.

        A rejection recorded by the Ledger before a Lifecycle write can fail only
        after the gateway has decided not to dispatch (or the adapter explicitly
        returned a rejection). It is local terminal evidence, so recovery must not
        manufacture broker evidence or require a new external query.
        """
        current = self._ledger.status(request_id)
        if current not in (
            ExecutionLedgerStatus.REJECTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        ):
            raise ValueError("Ledger não contém rejeição durável recuperável.")

        lifecycle = self._lifecycle.get(request_id)
        if lifecycle is not None and lifecycle.state is ExecutionLifecycleState.REJECTED:
            return
        if lifecycle is not None and lifecycle.state not in (
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.UNKNOWN,
        ):
            raise ValueError("Lifecycle não está em estado recuperável.")

        message = "Lifecycle recuperado a partir da rejeição durável do Ledger; nenhum dispatch adicional permitido."
        if lifecycle is None:
            self._lifecycle.reconcile_missing(
                request_id,
                ExecutionLifecycleState.REJECTED,
                updated_at=datetime.now(timezone.utc),
                message=message,
            )
        else:
            self._lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.REJECTED,
                updated_at=datetime.now(timezone.utc),
                message=message,
            )

    def reconcile_unknown(self, request_id: str, *, observation: ExternalOrderObservation) -> None:
        """Resolve an uncertain REAL execution only from explicit external evidence."""
        with self._coordination.acquire():
            return self._reconcile_unknown_locked(request_id, observation=observation)

    def _reconcile_unknown_locked(self, request_id: str, *, observation: ExternalOrderObservation) -> None:
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa obrigatória para reconciliação REAL.")
        if observation.status not in (
            ExternalOrderStatus.EXECUTED,
            ExternalOrderStatus.NOT_EXECUTED,
        ):
            raise ValueError("observação externa ainda não é conclusiva.")
        current = self._ledger.status(request_id)
        if current is not None and current not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        lifecycle = self._lifecycle.get(request_id)
        if lifecycle is not None and lifecycle.state not in (
            ExecutionLifecycleState.UNKNOWN,
            ExecutionLifecycleState.PENDING,
        ):
            raise ValueError("Lifecycle não está em estado incerto reconciliável.")

        ledger_external_id = self._ledger.external_id(request_id)
        observed_external_id = observation.external_id.strip()
        # Reconciliation is a recovery boundary, not an identity-assignment
        # boundary. If the request never durably recorded an external broker
        # reference, a caller-supplied ID is not proof that this request created
        # that external order. Keep the request unresolved instead of allowing
        # identity injection to promote UNKNOWN/RESERVED.
        if ledger_external_id is None:
            raise ValueError("request_id não possui external_id durável para reconciliação.")
        if ledger_external_id != observed_external_id:
            raise ValueError("external_id observado difere do external_id durável do Ledger.")

        executed = observation.status is ExternalOrderStatus.EXECUTED
        self._ledger.reconcile(
            request_id,
            executed=executed,
            external_id=observed_external_id,
        )
        target = (
            ExecutionLifecycleState.ACCEPTED
            if executed
            else ExecutionLifecycleState.REJECTED
        )
        try:
            if lifecycle is None:
                self._lifecycle.reconcile_missing(
                    request_id,
                    target,
                    updated_at=datetime.now(timezone.utc),
                    message=f"reconciliação REAL por evidência externa: {observation.message}",
                )
            else:
                self._lifecycle.reconcile(
                    request_id,
                    target,
                    updated_at=datetime.now(timezone.utc),
                    message=f"reconciliação REAL por evidência externa: {observation.message}",
                )
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Ledger reconciliado, mas Lifecycle não foi reconciliado; recuperação necessária: {exc}"
            ) from exc
