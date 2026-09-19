from __future__ import annotations

from dataclasses import dataclass
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.kill_switch import KillSwitch
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from execution.p124_broker_session import BrokerSessionBoundary, BrokerSessionObservation
from core.request_identity import validate_request_id
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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, kill_switch: KillSwitch) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch é obrigatório para execução REAL.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._kill_switch = kill_switch
        self._persistence_fault = False

    @staticmethod
    def _safe_adapter_message(execution: ExecutionResult | None) -> str:
        if execution is None:
            return "resultado REAL não confirmado."
        return "ordem REAL aceita." if execution.accepted else "ordem REAL rejeitada pelo adapter."

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or isinstance(request.amount, bool) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, session: BrokerSessionObservation | None = None) -> RealGatewayResult:
        try:
            validate_request_id(request_id)
        except ValueError:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if self._persistence_fault:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "persistência REAL em estado de falha; novas execuções bloqueadas até recuperação.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if session is None:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL autenticada e vinculada à conta é obrigatória.")
        try:
            session = BrokerSessionBoundary.validate(session)
        except ValueError:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL inválida.")
        if not BrokerSessionBoundary.is_usable(session):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL não está autenticada.")
        if session.account_id != authorization.account_id or session.session_id != authorization.session_id:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "sessão REAL não corresponde à autorização ativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        try:
            with self._kill_switch.execution_window():
                if not self._valid_request(request):
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
                try:
                    validate_request_id(request.request_id)
                except ValueError:
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "request.request_id inválido.")
                if request.request_id != request_id:
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id externo deve ser idêntico ao request.request_id.")
                if not isinstance(broker, str) or not broker.strip():
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
                if broker.strip().lower() != authorization.broker_id.strip().lower():
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
                try:
                    actual_adapter_id = self._gateway.adapter_id(broker)
                except Exception:
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "adapter REAL não está registrado.")
                if actual_adapter_id.casefold() != authorization.adapter_id.strip().casefold():
                    return RealGatewayResult(RealGatewayStatus.REJECTED, "adapter da requisição difere da autorização.")

                current_status = self._ledger.status(request_id)
                if current_status is not None:
                    if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.")
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")

                try:
                    self._ledger.reserve(request_id)
                except (OSError, ValueError):
                    return RealGatewayResult(RealGatewayStatus.BLOCKED, "não foi possível reservar request_id com segurança; envio bloqueado.")

                try:
                    result = self._gateway.execute(broker, request, allow_real=True)
                except Exception:
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        self._persistence_fault = True
                        return RealGatewayResult(RealGatewayStatus.BLOCKED, "falha de persistência após resultado REAL incerto; novas execuções bloqueadas.")
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, "resultado REAL incerto após falha no boundary do adapter; reconciliação explícita necessária.")

                if result.execution is None:
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        self._persistence_fault = True
                        return RealGatewayResult(RealGatewayStatus.BLOCKED, "falha de persistência após resultado REAL incerto; novas execuções bloqueadas.")
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, "resultado REAL sem execução confirmável; reconciliação explícita necessária.")

                if not result.execution.accepted:
                    try:
                        self._ledger.mark_rejected(request_id)
                    except (OSError, ValueError):
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, "ordem rejeitada, mas persistência do estado falhou; reconciliação necessária.", result.execution)
                    return RealGatewayResult(RealGatewayStatus.REJECTED, self._safe_adapter_message(result.execution), result.execution)

                if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id e persistência também falhou; reconciliação necessária.", result.execution)
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

                try:
                    self._ledger.mark_accepted(
                        request_id,
                        broker=broker,
                        adapter=authorization.adapter_id,
                        external_id=result.execution.external_id.strip(),
                    )
                except (OSError, ValueError):
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        self._persistence_fault = True
                        return RealGatewayResult(RealGatewayStatus.BLOCKED, "falha de persistência após aceite REAL; novas execuções bloqueadas.", result.execution)
                    return RealGatewayResult(RealGatewayStatus.UNKNOWN, "ordem REAL aceita, mas identidade/estado não pôde ser confirmado; reconciliação explícita necessária.", result.execution)
                return RealGatewayResult(RealGatewayStatus.ADMITTED, self._safe_adapter_message(result.execution), result.execution)
        except RuntimeError:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativo na fronteira final de execução REAL.")

    def reconcile_unknown(
        self,
        request_id: str,
        *,
        broker: str,
        adapter: str,
        external_id: str,
        status: str,
        observed_at,
        source: str,
    ) -> None:
        """Reconcile only from explicit external evidence; never resubmits."""
        self._ledger.reconcile_with_evidence(
            request_id,
            broker=broker,
            adapter=adapter,
            external_id=external_id,
            status=status,
            observed_at=observed_at,
            source=source,
        )
