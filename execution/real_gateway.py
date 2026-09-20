from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math

from core.kill_switch import KillSwitch
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
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

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if isinstance(request.amount, bool) or not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport) -> RealGatewayResult:
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not isinstance(request, ExecutionRequest):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id is not None and request.request_id != request_id:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id do envelope difere do request_id da requisição.")
        request = replace(request, request_id=request_id)
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")

        current_status = self._ledger.status(request_id)
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.",
                )
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        timestamp = datetime.now(timezone.utc)
        try:
            self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, timestamp, "execução REAL iniciada"))
            self._ledger.reserve(request_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        # Re-check the live kill switch immediately before external dispatch.
        if not self._kill_switch.allows_execution():
            reason = self._kill_switch.state.reason or "kill switch ativo"
            try:
                self._ledger.reconcile(request_id, executed=False)
                self._lifecycle.reconcile(request_id, ExecutionLifecycleState.REJECTED, updated_at=datetime.now(timezone.utc), message=f"execução não enviada: {reason}")
            except (OSError, ValueError):
                self._mark_lifecycle_unknown(request_id, timestamp, f"kill switch bloqueou antes do dispatch, mas a persistência falhou: {reason}")
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"execução REAL bloqueada pelo kill switch: {reason}")

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            self._mark_lifecycle_unknown(request_id, timestamp, f"resultado REAL incerto: {type(exc).__name__}: {exc}")
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            self._mark_lifecycle_unknown(request_id, timestamp, result.message)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, timestamp, result.execution.message))
            except (OSError, ValueError) as exc:
                self._mark_lifecycle_unknown(request_id, timestamp, f"ordem rejeitada, mas persistência do estado falhou: {exc}")
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
                self._mark_lifecycle_unknown(request_id, timestamp, "aceite REAL sem external_id")
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            # Persist the broker identity before terminal state. If the process dies
            # after this point, recovery can query the exact external order without replay.
            self._ledger.bind_external_id(request_id, result.execution.external_id.strip())
            self._ledger.mark_accepted(request_id, external_id=result.execution.external_id.strip())
            self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.ACCEPTED, timestamp, result.execution.message))
        except (OSError, ValueError) as exc:
            self._mark_lifecycle_unknown(request_id, timestamp, f"ordem REAL aceita, mas persistência falhou: {exc}")
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def _mark_lifecycle_unknown(self, request_id: str, timestamp: datetime, message: str) -> None:
        try:
            current = self._lifecycle.get(request_id)
            if current is None:
                self._lifecycle.reconstruct_unknown(
                    request_id,
                    updated_at=timestamp,
                    message=message,
                )
            elif current.state is ExecutionLifecycleState.PENDING:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, timestamp, message))
        except (OSError, ValueError):
            pass

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        """Explicitly reconcile UNKNOWN/RESERVED; never resubmits the external order."""
        if self._ledger.status(request_id) not in (
            ExecutionLedgerStatus.UNKNOWN,
            ExecutionLedgerStatus.RESERVED,
        ):
            raise ValueError("request_id não está em estado incerto reconciliável.")

        # Recovery may find a ledger-only RESERVED/UNKNOWN record after a crash
        # between the two durable stores. Materialize UNKNOWN in lifecycle first
        # so the lifecycle side can never silently disappear while the ledger is
        # being reconciled. This still never re-submits the external order.
        current = self._lifecycle.get(request_id)
        timestamp = datetime.now(timezone.utc)
        if current is None:
            self._lifecycle.reconstruct_unknown(
                request_id,
                updated_at=timestamp,
                message="estado reconstruído durante reconciliação explícita",
            )
        elif current.state not in (ExecutionLifecycleState.UNKNOWN, ExecutionLifecycleState.PENDING):
            raise ValueError("lifecycle não está em estado reconciliável.")

        self._ledger.reconcile(request_id, executed=executed)
        state = ExecutionLifecycleState.ACCEPTED if executed else ExecutionLifecycleState.REJECTED
        self._lifecycle.reconcile(
            request_id,
            state,
            updated_at=datetime.now(timezone.utc),
            message="reconciliação explícita concluída",
        )
