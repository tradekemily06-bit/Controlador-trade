from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore, ExecutionLifecycleRecord
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
        self._processed_request_ids: set[str] = set(ledger.records())

    def _lifecycle_put(self, request_id: str, state: ExecutionLifecycleState, message: str, *, request: ExecutionRequest | None = None, external_id: str | None = None) -> bool:
        if self._lifecycle is None:
            return True
        try:
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id=request_id,
                    state=state,
                    updated_at=datetime.now(timezone.utc),
                    message=message,
                    decision_id=None if request is None else request.decision_id,
                    symbol=None if request is None else request.symbol,
                    signal=None if request is None else request.signal.value,
                    amount=None if request is None else request.amount,
                    mode=None if request is None else request.mode.value,
                    external_id=external_id,
                )
            )
            return True
        except (OSError, ValueError):
            return False

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
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
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

        try:
            self._ledger.reserve(request_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        # Ledger is the no-replay authority. Lifecycle is a secondary durable
        # projection; failure here must fail closed before any broker call.
        if not self._lifecycle_put(request_id, ExecutionLifecycleState.PENDING, "REAL request reservado; aguardando resultado externo.", request=request):
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "não foi possível persistir o lifecycle REAL com segurança antes do envio.")

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            message = f"resultado REAL incerto: {type(exc).__name__}: {exc}"
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            if not self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, message, request=request):
                message += " lifecycle também não pôde ser persistido."
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, message)

        if result.uncertain:
            message = result.message
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                message += f" ledger também não pôde ser persistido: {exc}"
            if not self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, message, request=request, external_id=result.execution.external_id if result.execution else None):
                message += " lifecycle também não pôde ser persistido."
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, message, result.execution)

        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, result.message, request=request)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
            except (OSError, ValueError) as exc:
                self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, f"rejeição externa; persistência do ledger falhou: {exc}", request=request, external_id=result.execution.external_id)
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            if not self._lifecycle_put(request_id, ExecutionLifecycleState.REJECTED, result.execution.message, request=request, external_id=result.execution.external_id):
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, "ordem rejeitada, mas lifecycle não pôde ser persistido com segurança.", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", request=request)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.mark_accepted(request_id)
        except (OSError, ValueError) as exc:
            self._lifecycle_put(request_id, ExecutionLifecycleState.UNKNOWN, f"ordem aceita externamente; persistência do ledger falhou: {exc}", request=request, external_id=result.execution.external_id)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)

        if not self._lifecycle_put(request_id, ExecutionLifecycleState.ACCEPTED, result.execution.message, request=request, external_id=result.execution.external_id):
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "ordem REAL aceita, mas lifecycle não pôde ser persistido; reconciliação necessária.", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        """Reconcile both durable projections idempotently; never resubmit."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        target_ledger = ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
        target_lifecycle = ExecutionLifecycleState.ACCEPTED if executed else ExecutionLifecycleState.REJECTED

        ledger_state = self._ledger.status(request_id)
        if ledger_state in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
            self._ledger.reconcile(request_id, executed=executed)
            ledger_state = self._ledger.status(request_id)
        elif ledger_state is None:
            raise ValueError("request_id não existe no ledger.")
        elif ledger_state is not target_ledger:
            expected = "RECONCILED_EXECUTED" if executed else "RECONCILED_NOT_EXECUTED"
            raise ValueError(f"ledger incompatível com a reconciliação esperada: {ledger_state.value} != {expected}.")

        if self._lifecycle is None:
            return
        lifecycle = self._lifecycle.get(request_id)
        if lifecycle is None:
            raise ValueError("request_id não existe no lifecycle.")
        if lifecycle.state is ExecutionLifecycleState.UNKNOWN:
            self._lifecycle.reconcile(
                request_id,
                target_lifecycle,
                updated_at=datetime.now(timezone.utc),
                message="reconciliação explícita; nenhuma nova ordem foi enviada.",
            )
            return
        if lifecycle.state is not target_lifecycle:
            raise ValueError("lifecycle incompatível com a reconciliação esperada.")
