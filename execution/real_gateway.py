from __future__ import annotations

from dataclasses import dataclass

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger | None = None) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._processed_request_ids: set[str] = set(ledger.records()) if ledger else set()

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
        if request.mode is not ExecutionMode.REAL:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "gateway REAL exige request em modo REAL.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")

        if request_id in self._processed_request_ids:
            status = self._ledger.status(request_id) if self._ledger is not None else ExecutionLedgerStatus.ACCEPTED
            if status is ExecutionLedgerStatus.UNKNOWN:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, "request_id está em estado UNKNOWN; reconciliação explícita obrigatória antes de qualquer novo envio.")
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        if self._ledger is not None:
            try:
                self._ledger.reserve(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")
            self._processed_request_ids.add(request_id)

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            if self._ledger is not None:
                try:
                    self._ledger.mark_unknown(request_id)
                except (OSError, ValueError):
                    pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            if self._ledger is not None:
                try:
                    self._ledger.mark_unknown(request_id)
                except (OSError, ValueError):
                    pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if not result.execution.accepted:
            if self._ledger is not None:
                try:
                    self._ledger.mark_rejected(request_id)
                except (OSError, ValueError) as exc:
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        if self._ledger is not None:
            try:
                self._ledger.mark_accepted(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        """Explicitly reconcile an UNKNOWN request; never resubmits the order."""
        if self._ledger is None:
            raise ValueError("ledger é obrigatório para reconciliação explícita.")
        if self._ledger.status(request_id) is not ExecutionLedgerStatus.UNKNOWN:
            raise ValueError("request_id não está em estado UNKNOWN.")
        self._ledger.reconcile(request_id, executed=executed)
