from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.kill_switch import KillSwitch
from execution.adapter_gateway import BrokerAdapterGateway
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from core.p121_external_order_reconciliation import ExternalOrderQueryPort, ExternalOrderReconciliationBoundary


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

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore | None = None, kill_switch: KillSwitch | None = None) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch ao vivo é obrigatório para execução REAL.")
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
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
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
        if request.request_id is not None and (
            not isinstance(request.request_id, str) or request.request_id.strip() != request_id.strip()
        ):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id do gateway difere do request_id da ordem.")
        if self._kill_switch is not None and not self._kill_switch.allows_execution():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativado; dispatch REAL bloqueado.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if admission.broker_id.strip().lower() != broker.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da admissão difere do broker da requisição.")
        if admission.audit_id.strip() != authorization.audit_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "auditoria da admissão difere da autorização REAL.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        if broker.strip().lower() != authorization.broker_id.strip().lower():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")

        # A durable Lifecycle record is authoritative evidence that this request already
        # has an execution cycle. Never create a fresh Ledger reservation on top of
        # PENDING/UNKNOWN/terminal Lifecycle state, even if the Ledger is missing.
        if self._lifecycle is not None:
            existing_lifecycle = self._lifecycle.get(request_id)
            if existing_lifecycle is not None:
                if existing_lifecycle.state is ExecutionLifecycleState.UNKNOWN:
                    return RealGatewayResult(
                        RealGatewayStatus.UNKNOWN,
                        "Lifecycle UNKNOWN requer reconciliação explícita; novo dispatch REAL bloqueado.",
                    )
                return RealGatewayResult(
                    RealGatewayStatus.BLOCKED,
                    "request_id já possui ciclo Lifecycle; novo dispatch REAL recusado.",
                )

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
            self._ledger.reserve(request_id, broker_id=broker.strip())
            if self._lifecycle is not None:
                try:
                    self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)))
                except (OSError, ValueError) as exc:
                    try:
                        self._ledger.mark_unknown(request_id)
                    except (OSError, ValueError):
                        pass
                    return RealGatewayResult(
                        RealGatewayStatus.BLOCKED,
                        f"ciclo Lifecycle não pôde ser iniciado com segurança; dispatch REAL não realizado: {exc}",
                    )
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {exc}")

        if self._kill_switch is not None and not self._kill_switch.allows_execution():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "kill switch ativado imediatamente antes do dispatch REAL.")

        # Bind the canonical gateway request ID into legacy DTOs that omit it.
        # A supplied, different ID remains a hard rejection above.
        dispatch_request = (
            request
            if request.request_id is not None
            else replace(request, request_id=request_id)
        )

        try:
            result = self._gateway.execute(
                broker,
                dispatch_request,
                expected_adapter_id=authorization.adapter_id,
            )
        except Exception as exc:
            self._mark_unknown(request_id, f"resultado REAL incerto: {type(exc).__name__}: {exc}")
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {type(exc).__name__}: {exc}")

        if result.execution is None:
            self._mark_unknown(request_id, result.message)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message)

        if result.ambiguous:
            self._mark_unknown(request_id, result.message)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, result.message, result.execution)

        if not result.execution.accepted:
            # A rejection carrying an external reference is ambiguous: the broker
            # may have accepted the order while the adapter classified the response
            # as rejected. Preserve the reference and fail closed into UNKNOWN.
            if isinstance(result.execution.external_id, str) and result.execution.external_id.strip():
                try:
                    self._ledger.attach_external_id(request_id, result.execution.external_id)
                    self._ledger.mark_unknown(request_id)
                    self._mark_lifecycle(request_id, ExecutionLifecycleState.UNKNOWN, result.execution.message)
                except (OSError, ValueError) as exc:
                    return RealGatewayResult(
                        RealGatewayStatus.UNKNOWN,
                        f"resultado ambíguo com external_id, mas persistência falhou: {exc}",
                        result.execution,
                    )
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "adapter marcou rejeição com external_id; reconciliação explícita necessária.",
                    result.execution,
                )
            try:
                self._ledger.mark_rejected(request_id)
                self._mark_lifecycle(request_id, ExecutionLifecycleState.REJECTED, result.execution.message)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {exc}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, result.execution.message, result.execution)

        # An accepted REAL result without a durable broker/exchange reference is
        # ambiguous: the external order may exist but cannot be safely reconciled.
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            self._mark_unknown(request_id, "aceite REAL sem external_id; reconciliação explícita necessária.")
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)

        try:
            self._ledger.attach_external_id(request_id, result.execution.external_id)
            self._ledger.mark_accepted(request_id, external_id=result.execution.external_id)
            self._mark_lifecycle(request_id, ExecutionLifecycleState.ACCEPTED, result.execution.message)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência do estado falhou: {exc}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, result.execution.message, result.execution)

    def _mark_lifecycle(self, request_id: str, state: ExecutionLifecycleState, message: str) -> None:
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

    def _mark_unknown(self, request_id: str, message: str) -> None:
        try:
            self._ledger.mark_unknown(request_id)
            self._mark_lifecycle(request_id, ExecutionLifecycleState.UNKNOWN, message)
        except (OSError, ValueError):
            # The ledger remains authoritative for replay prevention even when
            # the secondary lifecycle projection cannot be persisted.
            pass

    def reconcile_unknown(self, request_id: str, *, query_port: ExternalOrderQueryPort):
        """Reconcile only through the external-evidence boundary; never accepts caller-supplied execution flags."""
        if self._lifecycle is None:
            raise ValueError("reconciliação REAL exige Lifecycle persistente.")
        if not isinstance(query_port, ExternalOrderQueryPort):
            raise ValueError("query_port de reconciliação inválido.")
        return ExternalOrderReconciliationBoundary().reconcile_request(
            request_id=request_id,
            ledger=self._ledger,
            lifecycle=self._lifecycle,
            query_port=query_port,
        )
