from __future__ import annotations

from dataclasses import dataclass
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderQueryPort, ExternalOrderReconciliationBoundary, ExternalOrderStatus, ReconciliationResult
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from security.production_operation_gate import ProductionOperationGate
from storage.production_boundary import ProductionStoragePolicy


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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, external_order_query: ExternalOrderQueryPort | None = None, production_gate: ProductionOperationGate | None = None) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._processed_request_ids: set[str] = set(ledger.records())
        self._external_order_query = external_order_query
        self._production_gate = production_gate or ProductionOperationGate(ProductionStoragePolicy())

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest):
            return False
        if request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.account_id, str) or not request.account_id.strip():
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
        if request.account_id.strip() != authorization.account_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "account_id da requisição difere da autorização.")
        if (
            admission.subject_id != authorization.subject_id
            or admission.tenant_id != authorization.tenant_id
            or admission.account_id != authorization.account_id
            or admission.broker_id.strip().lower() != authorization.broker_id.strip().lower()
        ):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "escopo de identidade/conta da admissão difere da autorização.")

        try:
            self._production_gate.authorize(
                subject_id=authorization.subject_id,
                tenant_id=authorization.tenant_id,
            )
        except (PermissionError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"production gate bloqueou a operação REAL: {exc}")

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
            self._ledger.reserve_real(request_id, broker_id=broker, symbol=request.symbol, account_id=authorization.account_id)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

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
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.mark_accepted_real(request_id, external_id=result.execution.external_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def reconcile_external_observation(
        self,
        request_id: str,
        observation: ExternalOrderObservation,
        *,
        evidence_id: str,
        evidence_source: str,
    ) -> ReconciliationResult:
        """Apply a broker observation to the authoritative REAL ledger; never resubmits."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if self._external_order_query is None:
            raise RuntimeError("fonte confiável de consulta externa não configurada; reconciliação manual é bloqueada.")
        observed = self._external_order_query.query_order(observation.external_id)
        if not isinstance(observed, ExternalOrderObservation):
            raise ValueError("fonte externa retornou observação inválida.")
        if observed != observation:
            raise ValueError("observação fornecida difere da observação obtida pela fonte externa confiável.")
        boundary = ExternalOrderReconciliationBoundary()
        result = boundary.reconcile(observed.external_id, observed)
        current = self._ledger.status(request_id)
        context = self._ledger.execution_context(request_id)
        if context is None:
            raise ValueError("request_id não possui contexto REAL no ledger.")
        linked_external_id = context.get("external_id")
        if linked_external_id not in (None, result.external_id):
            raise ValueError("external_id observado difere da identidade REAL persistida.")
        if linked_external_id is None:
            raise ValueError("operação REAL sem external_id persistido não pode ser reconciliada por observação externa.")

        if result.status in (ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN):
            return ReconciliationResult(
                external_id=result.external_id,
                status=result.status,
                reconciled=False,
                message=f"operação {request_id} permanece sem estado terminal: {result.message}",
            )

        if current in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
            self._ledger.reconcile(
                request_id,
                executed=result.status is ExternalOrderStatus.EXECUTED,
                evidence_id=evidence_id,
                evidence_source=evidence_source,
            )
            return ReconciliationResult(
                external_id=result.external_id,
                status=result.status,
                reconciled=True,
                message=f"operação {request_id} reconciliada no ledger: {result.message}",
            )

        if current is ExecutionLedgerStatus.ACCEPTED:
            if result.status is ExternalOrderStatus.NOT_EXECUTED:
                raise ValueError("observação externa contradiz um aceite REAL já persistido.")
            return ReconciliationResult(
                external_id=result.external_id,
                status=result.status,
                reconciled=True,
                message=f"operação {request_id} já está aceita no ledger; observação externa confirma o aceite.",
            )

        if current is ExecutionLedgerStatus.REJECTED and result.status is ExternalOrderStatus.EXECUTED:
            raise ValueError("observação externa contradiz uma rejeição REAL já persistida.")

        return ReconciliationResult(
            external_id=result.external_id,
            status=result.status,
            reconciled=False,
            message=f"operação {request_id} já possui estado terminal {current.value}; nenhuma mutação aplicada.",
        )

    def reconcile_unknown(
        self,
        request_id: str,
        *,
        executed: bool,
        evidence_id: str,
        evidence_source: str,
    ) -> None:
        """Reject caller-supplied REAL reconciliation evidence.

        REAL state resolution must come from the trusted external observation
        path. This compatibility method remains fail-closed so arbitrary
        caller input cannot turn UNKNOWN/RESERVED into a terminal state.
        """
        raise RuntimeError(
            "reconciliação REAL manual bloqueada; use "
            "reconcile_external_observation() com uma fonte externa confiável."
        )
