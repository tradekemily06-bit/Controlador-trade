from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import uuid
from typing import Callable

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary
from core.real_execution_confirmation import (
    ExecutionConfirmation,
    RealExecutionRequest,
    new_real_confirmation,
)
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState
from execution.ports import ExecutionMode
from execution.real_gateway import RealExecutionGateway, RealGatewayResult, RealGatewayStatus
from integration.persistent_broker_connection import PersistentBrokerConnectionRuntime


@dataclass(frozen=True)
class RealExecutionRuntimeStatus:
    mode: ExecutionMode
    real_enabled: bool
    broker_state: str
    broker_available: bool
    authorization_active: bool
    pending_confirmation_ids: tuple[str, ...]
    ledger_unknown_request_ids: tuple[str, ...]
    lifecycle_unknown_request_ids: tuple[str, ...]
    message: str


class RealExecutionRuntime:
    """Application boundary for guarded REAL execution.

    This object owns mode selection, persistent broker observability and
    one-shot user confirmations. It never calls a broker adapter directly;
    every REAL order must pass through RealExecutionGateway.
    """

    def __init__(
        self,
        *,
        broker_id: str,
        adapter_id: str,
        broker_connection: PersistentBrokerConnectionRuntime,
        gateway: RealExecutionGateway,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
        real_enabled: bool = False,
        audit_verified: bool = False,
        recovery_safe: Callable[[], bool] | None = None,
        market_healthy: Callable[[], bool] | None = None,
        risk_approved: Callable[[], bool] | None = None,
        kill_switch_clear: Callable[[], bool] | None = None,
    ) -> None:
        if not broker_id.strip() or not adapter_id.strip():
            raise ValueError("broker_id e adapter_id são obrigatórios.")
        self._broker_id = broker_id.strip()
        self._adapter_id = adapter_id.strip()
        self._connection = broker_connection
        self._gateway = gateway
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._real_enabled = bool(real_enabled)
        self._audit_verified = bool(audit_verified)
        self._recovery_safe = recovery_safe or (lambda: False)
        self._market_healthy = market_healthy or (lambda: False)
        self._risk_approved = risk_approved or (lambda: False)
        self._kill_switch_clear = kill_switch_clear or (lambda: False)
        self._safety_gate = RealSafetyGate()
        self._admission_boundary = RealAdmissionBoundary()
        self._lock = threading.RLock()
        self._mode = ExecutionMode.DEMO
        self._confirmations: dict[str, ExecutionConfirmation] = {}

    def start(self) -> None:
        self._connection.start()

    def user_disconnect(self) -> None:
        self._connection.user_disconnect()

    def select_mode(self, mode: ExecutionMode) -> None:
        if not isinstance(mode, ExecutionMode):
            raise ValueError("modo de execução inválido.")
        with self._lock:
            self._mode = mode

    def request_confirmation(self, *, request_id: str, phrase: str) -> ExecutionConfirmation:
        if self._mode is not ExecutionMode.REAL:
            raise ValueError("confirmação REAL só pode ser solicitada no modo REAL.")
        if not self._real_enabled:
            raise ValueError("execução REAL está desabilitada no runtime.")
        if self._ledger.status(request_id) is not None:
            raise ValueError("request_id já possui estado; nova confirmação não é permitida.")
        confirmation = new_real_confirmation(
            confirmation_id=f"real-confirm-{uuid.uuid4().hex}",
            request_id=request_id,
            phrase=phrase,
        )
        with self._lock:
            self._confirmations[confirmation.confirmation_id] = confirmation
        return confirmation

    def _build_guards(self) -> tuple[RealExecutionAuthorization, RealAdmission, RealSafetyReport]:
        connection = self._connection.status()
        authorization = RealExecutionAuthorization(
            authorization_id="runtime-real-authorization",
            audit_id="runtime-real-audit",
            broker_id=self._broker_id,
            adapter_id=self._adapter_id,
            explicitly_enabled=self._real_enabled,
            real_execution_allowed=self._real_enabled,
        )
        safety = self._safety_gate.evaluate(
            authorization_active=authorization.active,
            kill_switch_clear=bool(self._kill_switch_clear()),
            market_healthy=bool(self._market_healthy()),
            recovery_safe=bool(self._recovery_safe()),
            risk_approved=bool(self._risk_approved()),
            broker_available=connection.adapter_available and not connection.user_disconnected,
        )
        admission = self._admission_boundary.admit(
            admission_id="runtime-real-admission",
            audit_id="runtime-real-audit",
            audit_verified=self._audit_verified,
            authorization_active=authorization.active,
            safety_ready=safety.ready,
            broker_available=connection.adapter_available and not connection.user_disconnected,
            broker_id=self._broker_id,
        )
        return authorization, admission, safety

    def execute_confirmed(
        self,
        *,
        request_id: str,
        symbol: str,
        signal: Signal,
        amount: float,
        duration_seconds: int,
        confirmation_id: str,
    ) -> RealGatewayResult:
        with self._lock:
            if self._mode is not ExecutionMode.REAL:
                return RealGatewayResult(RealGatewayStatus.BLOCKED, "modo DEMO selecionado; REAL não será enviado.")
            confirmation = self._confirmations.get(confirmation_id)
            if confirmation is None:
                return RealGatewayResult(RealGatewayStatus.BLOCKED, "confirmação REAL não encontrada ou já consumida.")
            if confirmation.request_id != request_id:
                return RealGatewayResult(RealGatewayStatus.BLOCKED, "confirmação não corresponde ao request_id.")
            self._confirmations.pop(confirmation_id, None)

        try:
            real_request = RealExecutionRequest(
                request_id=request_id,
                symbol=symbol,
                signal=signal,
                amount=amount,
                duration_seconds=duration_seconds,
                confirmation=confirmation,
            )
            authorization, admission, safety = self._build_guards()
            if self._ledger.status(request_id) in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            ):
                return RealGatewayResult(
                    RealGatewayStatus.UNKNOWN,
                    "request_id está em estado incerto; reconciliação explícita é obrigatória.",
                )
            return self._gateway.execute(
                broker=self._broker_id,
                request_id=request_id,
                request=real_request.as_execution_request(),
                authorization=authorization,
                admission=admission,
                safety=safety,
            )
        except (TypeError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.REJECTED, f"requisição REAL inválida: {exc}")

    def status(self) -> RealExecutionRuntimeStatus:
        connection = self._connection.status()
        unknown_ledger = tuple(
            request_id for request_id in self._ledger.records()
            if self._ledger.status(request_id) in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED)
        )
        unknown_lifecycle = tuple(
            record.request_id for record in self._lifecycle.records()
            if record.state is ExecutionLifecycleState.UNKNOWN
        )
        authorization_active = self._real_enabled
        message = "REAL pronto para confirmação somente se todas as barreiras de segurança estiverem prontas."
        if connection.user_disconnected:
            message = "Conexão desligada pelo usuário; nenhuma reconexão automática está ativa."
        elif unknown_ledger or unknown_lifecycle:
            message = "Há execuções incertas; reconciliação explícita é obrigatória antes de novos envios."
        elif not self._real_enabled:
            message = "REAL permanece desabilitado por configuração segura."
        return RealExecutionRuntimeStatus(
            mode=self._mode,
            real_enabled=self._real_enabled,
            broker_state=connection.state,
            broker_available=connection.adapter_available and not connection.user_disconnected,
            authorization_active=authorization_active,
            pending_confirmation_ids=tuple(sorted(self._confirmations)),
            ledger_unknown_request_ids=unknown_ledger,
            lifecycle_unknown_request_ids=unknown_lifecycle,
            message=message,
        )
