from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.decision_snapshot import DecisionSnapshot
from core.ecosystem_maintenance import MaintenanceManager
from core.ecosystem_incidents import EcosystemIncidentManager
from core.kill_switch import KillSwitch
from core.models import Signal
from core.operational_safety_store import OperationalSafetyStore
from core.p4_operational_recorder import P4OperationalRecorder, RecordedOperation
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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
        maintenance: MaintenanceManager | None = None,
        safety_store: OperationalSafetyStore | None = None,
        incident_manager: EcosystemIncidentManager | None = None,
    ) -> None:
        if executor is None:
            raise ValueError("executor é obrigatório.")
        if kill_switch is None:
            raise ValueError("kill_switch é obrigatório.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise ValueError("safety_store inválido.")
        if incident_manager is not None and not isinstance(incident_manager, EcosystemIncidentManager):
            raise ValueError("incident_manager inválido.")
        self._executor = executor
        self._kill_switch = kill_switch
        self._recorder = recorder
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._maintenance = maintenance
        self._safety_store = safety_store
        self._incident_manager = incident_manager
        self._processed_request_ids: set[str] = set(ledger.records()) if ledger else set()

    def _refresh_kill_switch(self) -> str | None:
        """Refresh the authoritative persisted kill switch before dispatch.

        A process-local KillSwitch cannot observe a safety change made by a
        different worker. When a durable safety store is configured, every
        execution attempt therefore re-reads the persisted state. Any read or
        validation failure fails closed and no executor dispatch is allowed.
        """
        if self._safety_store is None:
            return None
        try:
            _audit, persisted = self._safety_store.load()
            self._kill_switch.synchronize(persisted.state)
            return None
        except (OSError, ValueError, TypeError) as exc:
            return f"estado de segurança indisponível: {type(exc).__name__}"

    def _final_safety_barrier(self, *, now: datetime) -> str | None:
        """Re-check global safety immediately before executor dispatch."""
        refresh_error = self._refresh_kill_switch()
        if refresh_error is not None:
            return refresh_error
        if not self._kill_switch.allows_execution():
            return f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}"
        if self._maintenance is not None and self._maintenance.execution_blocked(now=now):
            return "execução bloqueada durante manutenção ativa do ecossistema."
        if self._incident_manager is not None and self._incident_manager.execution_blocked():
            active_ids = ", ".join(item.incident_id for item in self._incident_manager.active())
            return f"execução bloqueada por incidente técnico ativo: {active_ids}"
        return None

    def _abandon_reserved_request(self, request_id: str) -> None:
        """Never leave a reservation falsely reusable after a lifecycle conflict."""
        if self._ledger is None:
            return
        try:
            current = self._ledger.status(request_id)
            if current is ExecutionLedgerStatus.RESERVED:
                self._ledger.mark_unknown(request_id)
        except (OSError, ValueError):
            pass

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
        if self._maintenance is not None and self._maintenance.execution_blocked(now=event_time):
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada durante manutenção ativa do ecossistema.")
        if self._incident_manager is not None and self._incident_manager.execution_blocked():
            active_ids = ", ".join(item.incident_id for item in self._incident_manager.active())
            return GatewayResult(GatewayStatus.BLOCKED, f"execução bloqueada por incidente técnico ativo: {active_ids}")

        audit_record = None
        if snapshot is not None and self._recorder is not None:
            audit_record = self._recorder.record_decision(snapshot, timestamp=event_time)

        refresh_error = self._refresh_kill_switch()
        if refresh_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, refresh_error)
        if not self._kill_switch.allows_execution():
            return GatewayResult(GatewayStatus.BLOCKED, f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}")

        # The ledger reservation is the atomic cross-process idempotency barrier.
        # Checking memory first is only an optimization; reserve() is the
        # authoritative decision and must happen before dispatch.
        if request_id in self._processed_request_ids:
            return GatewayResult(GatewayStatus.DUPLICATE, "request_id já processado; execução duplicada recusada.")
        if self._ledger is not None:
            try:
                self._ledger.reserve(request_id)
            except (OSError, ValueError) as exc:
                current = self._ledger.status(request_id)
                if current is not None:
                    self._processed_request_ids.add(request_id)
                    if current in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                        return GatewayResult(GatewayStatus.BLOCKED, "request_id está em estado incerto; reconciliação explícita obrigatória antes de novo envio.")
                    return GatewayResult(GatewayStatus.DUPLICATE, "request_id já processado; execução duplicada recusada.")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"não foi possível reservar request_id com segurança: {exc}")
            self._processed_request_ids.add(request_id)

        if self._lifecycle is not None:
            existing = self._lifecycle.get(request_id)
            if existing is not None:
                self._abandon_reserved_request(request_id)
                if existing.state is ExecutionLifecycleState.UNKNOWN:
                    return GatewayResult(GatewayStatus.BLOCKED, "execução UNKNOWN requer reconciliação explícita; replay automático bloqueado.")
                return GatewayResult(GatewayStatus.DUPLICATE, "request_id já possui ciclo de execução; replay recusado.")
            try:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, event_time, "execução iniciada"))
            except (OSError, ValueError) as exc:
                self._abandon_reserved_request(request_id)
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"não foi possível persistir o início da execução: {exc}")

        final_safety_error = self._final_safety_barrier(now=event_time)
        if final_safety_error is not None:
            self._mark_unknown(request_id, event_time, f"barreira de segurança bloqueou o dispatch: {final_safety_error}")
            return GatewayResult(GatewayStatus.BLOCKED, final_safety_error)

        try:
            result = self._executor.execute(request)
        except Exception as exc:
            self._mark_unknown(request_id, event_time, f"resultado do executor é incerto: {type(exc).__name__}: {exc}")
            if self._incident_manager is not None:
                try:
                    self._incident_manager.open_incident(
                        title="Falha técnica na execução",
                        message=f"O executor apresentou uma falha inesperada ({type(exc).__name__}). O resultado da ordem ficou UNKNOWN e novas ordens foram bloqueadas para investigação.",
                    )
                except (ValueError, RuntimeError):
                    pass
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"executor falhou; resultado marcado como UNKNOWN: {type(exc).__name__}: {exc}")

        if not isinstance(result, ExecutionResult):
            self._mark_unknown(request_id, event_time, "executor retornou resultado inválido")
            if self._incident_manager is not None:
                try:
                    self._incident_manager.open_incident(
                        title="Resposta técnica inválida",
                        message="O executor retornou um formato inválido. O resultado da ordem ficou UNKNOWN e novas ordens foram bloqueadas para investigação.",
                    )
                except (ValueError, RuntimeError):
                    pass
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "executor retornou resultado inválido; execução marcada como UNKNOWN.")

        if not result.accepted:
            if self._ledger is not None:
                try:
                    self._ledger.mark_rejected(request_id)
                except (OSError, ValueError) as exc:
                    self._mark_unknown(request_id, event_time, f"execução rejeitada, mas ledger não foi persistido: {exc}")
                    return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução rejeitada, mas persistência falhou; estado UNKNOWN: {exc}", result)
            if self._lifecycle is not None:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, event_time, result.message))
            self._processed_request_ids.add(request_id)
            return GatewayResult(GatewayStatus.EXECUTION_REJECTED, result.message, result)

        if self._ledger is not None:
            try:
                self._ledger.mark_accepted(request_id)
            except (OSError, ValueError) as exc:
                self._mark_unknown(request_id, event_time, f"execução aceita, mas ledger não foi persistido: {exc}")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução aceita, mas persistência falhou; estado UNKNOWN: {exc}", result)
        if self._lifecycle is not None:
            try:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.ACCEPTED, event_time, result.message))
            except (OSError, ValueError) as exc:
                self._mark_unknown(request_id, event_time, f"execução aceita, mas persistência do ciclo falhou: {exc}")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução aceita, mas persistência do ciclo falhou; estado UNKNOWN: {exc}", result)

        self._processed_request_ids.add(request_id)
        recorded_operation = None
        if snapshot is not None and self._recorder is not None:
            recorded_operation = self._recorder.record_operation(snapshot, timestamp=event_time, entry_conditions=entry_conditions, audit_record=audit_record)

        return GatewayResult(GatewayStatus.ACCEPTED, result.message, result, recorded_operation)

    def _mark_unknown(self, request_id: str, timestamp: datetime, message: str) -> None:
        if self._ledger is not None:
            try:
                current_status = self._ledger.status(request_id)
                if current_status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                    self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
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
