from __future__ import annotations

from dataclasses import dataclass
import math

from core.decision_snapshot import DecisionSnapshot
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.risk_state_fingerprint import risk_state_identity
from core.risk_state_provider import read_authoritative_risk_state, RiskStateProvider
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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger,
                 risk_state_provider: RiskStateProvider) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(risk_state_provider, RiskStateProvider):
            raise ValueError("risk_state_provider autoritativo é obrigatório para execução REAL.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._risk_state_provider = risk_state_provider
        self._processed_request_ids: set[str] = set(ledger.records())

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        return type(exc).__name__

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

    def _revalidate_risk(self, snapshot: DecisionSnapshot) -> RealGatewayResult | None:
        identity = snapshot.risk_state_identity
        if not isinstance(identity, str) or not identity.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "identidade de risco da decisão está ausente; REAL bloqueado.")
        try:
            current_state = read_authoritative_risk_state(self._risk_state_provider)
            current_identity = risk_state_identity(current_state)
        except Exception as exc:
            return RealGatewayResult(
                RealGatewayStatus.UNKNOWN,
                f"não foi possível revalidar o estado de risco antes do dispatch: {self._safe_error(exc)}",
            )
        if current_identity != identity:
            return RealGatewayResult(
                RealGatewayStatus.BLOCKED,
                "estado de risco mudou desde a decisão; novo ciclo de decisão obrigatório antes do dispatch.",
            )
        return None

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, snapshot: DecisionSnapshot) -> RealGatewayResult:
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
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.")
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

        # Revalidate once before reserving and once after reservation. The second
        # check closes the stale-snapshot window immediately before broker dispatch.
        risk_result = self._revalidate_risk(snapshot)
        if risk_result is not None:
            return risk_result

        try:
            self._ledger.reserve(request_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {self._safe_error(exc)}")

        risk_result = self._revalidate_risk(snapshot)
        if risk_result is not None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            if risk_result.status == RealGatewayStatus.UNKNOWN:
                return risk_result
            return RealGatewayResult(RealGatewayStatus.BLOCKED, risk_result.message)

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {self._safe_error(exc)}")

        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {self._safe_error(exc)}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {self._safe_error(exc)}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.mark_accepted(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {self._safe_error(exc)}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        """Explicitly reconcile UNKNOWN/RESERVED; never resubmits the order."""
        if self._ledger.status(request_id) not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
            raise ValueError("request_id não está em estado incerto reconciliável.")
        self._ledger.reconcile(request_id, executed=executed)
