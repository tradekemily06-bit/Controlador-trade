from __future__ import annotations

from dataclasses import dataclass

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.adapter_gateway import BrokerAdapterGateway
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

    def __init__(self, adapter_gateway: BrokerAdapterGateway) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        self._gateway = adapter_gateway

    def execute(self, *, broker: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization,
                admission: RealAdmission,
                safety: RealSafetyReport) -> RealGatewayResult:
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if request.mode is not ExecutionMode.REAL:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "gateway REAL exige request em modo REAL.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        result = self._gateway.execute(broker, request)
        if result.execution is None:
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.message)
        if result.execution.accepted:
            return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)
        return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)
