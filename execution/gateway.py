from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch
from core.models import Signal
from core.p4_operational_recorder import P4OperationalRecorder, RecordedOperation
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionPort, ExecutionRequest, ExecutionResult


class GatewayStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    INVALID_REQUEST = "INVALID_REQUEST"
    BLOCKED = "BLOCKED"
    DUPLICATE = "DUPLICATE"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    EXECUTOR_ERROR = "EXECUTOR_ERROR"


@dataclass(frozen=True)
class GatewayResult:
    status: GatewayStatus
    message: str
    execution: ExecutionResult | None = None
    recorded_operation: RecordedOperation | None = None

    @property
    def accepted(self) -> bool:
        return self.status is GatewayStatus.ACCEPTED


class ExecutionGateway:
    """Broker-agnostic safety gateway. P5 permits only DEMO/PAPER execution."""

    def __init__(
        self,
        executor: ExecutionPort,
        kill_switch: KillSwitch,
        recorder: P4OperationalRecorder | None = None,
        ledger: ExecutionLedger | None = None,
        lifecycle: ExecutionLifecycleStore | None = None,
    ) -> None:
        if executor is None:
            raise ValueError("executor é obrigatório.")
        if kill_switch is None:
            raise ValueError("kill_switch é obrigatório.")
        self._executor = executor
        self._kill_switch = kill_switch
        self._recorder = recorder
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._processed_request_ids: set[str] = set(ledger.records()) if ledger else set()

    def execute(
        self,
        request_id: str,
        request: ExecutionRequest,
        *,
        snapshot: DecisionSnapshot | None = None,
        timestamp: datetime | None = None,
        entry_conditions: tuple[str, ...] = (),
    ) -> GatewayResult:
        validation_error = self._validate(request_id, request)
        if validation_error is not None:
            return GatewayResult(GatewayStatus.INVALID_REQUEST, validation_error)

        event_time = timestamp or datetime.now(timezone.utc)
        audit_record = None
        if snapshot is not None and self._recorder is not None:
            audit_record = self._recorder.record_decision(snapshot, timestamp=event_time)

        if not self._kill_switch.allows_execution():
            return GatewayResult(GatewayStatus.BLOCKED, f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}")

        if request_id in self._processed_request_ids or (self._ledger is not None and self._ledger.contains(request_id)):
            return GatewayResult(GatewayStatus.DUPLICATE, "request_id já processado; execução duplicada recusada.")

        if self._lifecycle is not None:
            existing = self._lifecycle.get(request_id)
            if existing is not None:
                if existing.state is ExecutionLifecycleState.UNKNOWN:
                    return GatewayResult(GatewayStatus.BLOCKED, "execução UNKNOWN requer reconciliação explícita; replay automático bloqueado.")
                if existing.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.ACCEPTED):
                    return GatewayResult(GatewayStatus.DUPLICATE, "request_id já possui ciclo de execução; replay recusado.")
            try:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, event_time, "execução iniciada"))
            except (OSError, ValueError) as exc:
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"não foi possível persistir o início da execução: {exc}")

        try:
            result = self._executor.execute(request)
        except Exception as exc:
            self._mark_unknown(request_id, event_time, f"resultado do executor é incerto: {type(exc).__name__}: {exc}")
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"executor falhou; resultado marcado como UNKNOWN: {type(exc).__name__}: {exc}")

        if not isinstance(result, ExecutionResult):
            self._mark_unknown(request_id, event_time, "executor retornou resultado inválido")
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "executor retornou resultado inválido; execução marcada como UNKNOWN.")

        if not result.accepted:
            if self._lifecycle is not None:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, event_time, result.message))
            return GatewayResult(GatewayStatus.EXECUTION_REJECTED, result.message, result)

        if self._ledger is not None:
            try:
                self._ledger.record(request_id)
            except (OSError, ValueError) as exc:
                self._mark_unknown(request_id, event_time, f"execução aceita, mas ledger não foi persistido: {exc}")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução aceita, mas persistência falhou; estado UNKNOWN: {exc}", result)
        if self._lifecycle is not None:
            try:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.ACCEPTED, event_time, result.message))
            except (OSError, ValueError) as exc:
                self._mark_unknown(request_id, event_time, f"execução aceita, mas ciclo não foi persistido: {exc}")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução aceita, mas persistência do ciclo falhou; estado UNKNOWN: {exc}", result)
        self._processed_request_ids.add(request_id)

        recorded_operation = None
        if snapshot is not None and self._recorder is not None:
            recorded_operation = self._recorder.record_operation(snapshot, timestamp=event_time, entry_conditions=entry_conditions, audit_record=audit_record)

        return GatewayResult(GatewayStatus.ACCEPTED, result.message, result, recorded_operation)

    def _mark_unknown(self, request_id: str, timestamp: datetime, message: str) -> None:
        if self._lifecycle is None:
            return
        try:
            current = self._lifecycle.get(request_id)
            if current is None:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, timestamp, message))
            elif current.state is not ExecutionLifecycleState.UNKNOWN:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.UNKNOWN, timestamp, message))
        except (OSError, ValueError):
            pass

    @staticmethod
    def _validate(request_id: str, request: ExecutionRequest) -> str | None:
        if not isinstance(request_id, str) or not request_id.strip():
            return "request_id não pode ser vazio."
        if not isinstance(request, ExecutionRequest):
            return "requisição de execução inválida."
        if request.mode is not ExecutionMode.DEMO:
            return "P5 aceita somente execução DEMO/PAPER nesta etapa."
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return "sinal AGUARDAR não pode ser executado."
        if not request.symbol.strip():
            return "Símbolo não pode ser vazio."
        if request.amount <= 0:
            return "Valor da execução deve ser positivo."
        if request.duration_seconds <= 0:
            return "Duração deve ser positiva."
        return None
