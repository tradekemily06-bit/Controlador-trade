from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch
from core.models import Signal
from core.p4_operational_recorder import P4OperationalRecorder, RecordedOperation
from execution.ports import ExecutionMode, ExecutionPort, ExecutionRequest, ExecutionResult


class GatewayStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    INVALID_REQUEST = "INVALID_REQUEST"
    BLOCKED = "BLOCKED"
    DUPLICATE = "DUPLICATE"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"


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

    def __init__(self, executor: ExecutionPort, kill_switch: KillSwitch, recorder: P4OperationalRecorder | None = None) -> None:
        self._executor = executor
        self._kill_switch = kill_switch
        self._recorder = recorder
        self._processed_request_ids: set[str] = set()

    def execute(self, request_id: str, request: ExecutionRequest, *, snapshot: DecisionSnapshot | None = None, timestamp: datetime | None = None, entry_conditions: tuple[str, ...] = ()) -> GatewayResult:
        validation_error = self._validate(request_id, request)
        if validation_error is not None:
            return GatewayResult(GatewayStatus.INVALID_REQUEST, validation_error)

        event_time = timestamp or datetime.now(timezone.utc)
        if not self._kill_switch.allows_execution():
            if snapshot is not None and self._recorder is not None:
                self._recorder.record_decision(snapshot, timestamp=event_time)
            return GatewayResult(GatewayStatus.BLOCKED, f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}")

        if request_id in self._processed_request_ids:
            return GatewayResult(GatewayStatus.DUPLICATE, "request_id já processado; execução duplicada recusada.")

        audit_record = None
        if snapshot is not None and self._recorder is not None:
            audit_record = self._recorder.record_decision(snapshot, timestamp=event_time)

        try:
            result = self._executor.execute(request)
        except Exception as exc:
            return GatewayResult(GatewayStatus.EXECUTION_REJECTED, f"executor falhou; execução não confirmada: {exc}")

        if not result.accepted:
            return GatewayResult(GatewayStatus.EXECUTION_REJECTED, result.message, result)

        self._processed_request_ids.add(request_id)

        recorded_operation = None
        if snapshot is not None and self._recorder is not None:
            recorded_operation = self._recorder.record_operation(snapshot, timestamp=event_time, entry_conditions=entry_conditions, audit_record=audit_record)

        return GatewayResult(GatewayStatus.ACCEPTED, result.message, result, recorded_operation)

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
