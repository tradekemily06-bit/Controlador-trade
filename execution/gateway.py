from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, TYPE_CHECKING

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.ecosystem_incidents import EcosystemIncidentManager
from core.ecosystem_maintenance import MaintenanceManager
from core.kill_switch import KillSwitch
from core.models import Signal
from core.operational_safety_store import OperationalSafetyStore
from core.p4_operational_recorder import P4OperationalRecorder, RecordedOperation
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionPort, ExecutionRequest, ExecutionResult

if TYPE_CHECKING:
    from core.global_operational_barrier import GlobalOperationalBarrier


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

    def __init__(self, executor: ExecutionPort, kill_switch: KillSwitch, recorder: P4OperationalRecorder | None = None, ledger: ExecutionLedger | None = None, lifecycle: ExecutionLifecycleStore | None = None, maintenance: MaintenanceManager | None = None, safety_store: OperationalSafetyStore | None = None, incident_manager: EcosystemIncidentManager | None = None, operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None, market_data_fingerprint_provider: Callable[[], str | None] | None = None, decision_freshness_policy: DecisionFreshnessPolicy | None = None, decision_clock: Callable[[], datetime] | None = None) -> None:
        if executor is None:
            raise ValueError("executor é obrigatório.")
        if kill_switch is None:
            raise ValueError("kill_switch é obrigatório.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise ValueError("safety_store inválido.")
        if incident_manager is not None and not isinstance(incident_manager, EcosystemIncidentManager):
            raise ValueError("incident_manager inválido.")
        if operational_barrier_provider is not None and not callable(operational_barrier_provider):
            raise ValueError("operational_barrier_provider inválido.")
        if market_data_fingerprint_provider is not None and not callable(market_data_fingerprint_provider):
            raise ValueError("market_data_fingerprint_provider inválido.")
        if decision_freshness_policy is not None and not isinstance(decision_freshness_policy, DecisionFreshnessPolicy):
            raise ValueError("decision_freshness_policy inválida.")
        if decision_clock is not None and not callable(decision_clock):
            raise ValueError("decision_clock inválido.")
        self._executor = executor
        self._kill_switch = kill_switch
        self._recorder = recorder
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._maintenance = maintenance
        self._safety_store = safety_store
        self._incident_manager = incident_manager
        self._operational_barrier_provider = operational_barrier_provider
        self._market_data_fingerprint_provider = market_data_fingerprint_provider
        self._decision_freshness_policy = decision_freshness_policy
        self._decision_clock = decision_clock or (lambda: datetime.now(timezone.utc))
        self._processed_request_ids: set[str] = set(ledger.records()) if ledger else set()

    def set_operational_barrier_provider(self, provider: Callable[[], GlobalOperationalBarrier]) -> None:
        """Attach the authoritative global barrier after runtime composition."""
        if not callable(provider):
            raise ValueError("operational barrier provider inválido.")
        self._operational_barrier_provider = provider

    def set_market_data_fingerprint_provider(self, provider: Callable[[], str | None]) -> None:
        """Attach the authoritative runtime market-data identity after composition."""
        if not callable(provider):
            raise ValueError("market-data fingerprint provider inválido.")
        self._market_data_fingerprint_provider = provider

    def set_decision_freshness_policy(self, policy: DecisionFreshnessPolicy, *, clock: Callable[[], datetime] | None = None) -> None:
        """Attach the authoritative freshness policy after runtime composition."""
        if not isinstance(policy, DecisionFreshnessPolicy):
            raise ValueError("decision freshness policy inválida.")
        if clock is not None and not callable(clock):
            raise ValueError("decision clock inválido.")
        self._decision_freshness_policy = policy
        if clock is not None:
            self._decision_clock = clock

    def _refresh_kill_switch(self) -> str | None:
        if self._safety_store is None:
            return None
        try:
            _audit, persisted = self._safety_store.load()
            self._kill_switch.synchronize(persisted.state)
            return None
        except (OSError, ValueError, TypeError) as exc:
            return f"estado de segurança indisponível: {type(exc).__name__}"

    def _incident_error(self) -> str | None:
        if self._incident_manager is None:
            return None
        try:
            if self._incident_manager.execution_blocked():
                status = self._incident_manager.status()
                reason = status.get("reason") or "problema técnico ativo ou estado de incidente indisponível"
                return f"execução bloqueada por incidente técnico: {reason}"
            return None
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            return f"estado de incidente indisponível: {type(exc).__name__}"

    def _global_barrier_error(self) -> str | None:
        provider = self._operational_barrier_provider
        if provider is None:
            return None
        try:
            barrier = provider()
            if barrier is None:
                return "barreira operacional global indisponível"
            decision = barrier.evaluate()
            if not decision.operationally_allowed:
                return f"execução bloqueada pela barreira operacional global: {decision.reason}"
            return None
        except Exception as exc:
            return f"barreira operacional global indisponível: {type(exc).__name__}"

    def _decision_freshness_error(self, *, created_at: datetime, now: datetime | None = None) -> str | None:
        policy = self._decision_freshness_policy
        if policy is None:
            return None
        try:
            current = now or self._decision_clock()
            return policy.validate(created_at, now=current)
        except Exception as exc:
            return f"execução bloqueada: estado de frescor da decisão indisponível: {type(exc).__name__}"

    def _decision_snapshot_error(self, request: ExecutionRequest, snapshot: DecisionSnapshot | None) -> str | None:
        """Require and validate the immutable decision record at the operational boundary."""
        if self._operational_barrier_provider is not None and self._decision_freshness_policy is not None and snapshot is None:
            return "execução bloqueada: snapshot da decisão é obrigatório no runtime operacional"
        if snapshot is None:
            return None
        if not snapshot.actionable:
            return "execução bloqueada: snapshot da decisão não é acionável"
        if str(snapshot.decision).upper() != "EXECUTAR":
            return "execução bloqueada: snapshot da decisão não é EXECUTAR"
        if snapshot.symbol != request.symbol:
            return "execução bloqueada: símbolo da requisição diverge do snapshot da decisão"
        if snapshot.signal != request.signal.value:
            return "execução bloqueada: sinal da requisição diverge do snapshot da decisão"
        if not isinstance(snapshot.timeframe, str) or not snapshot.timeframe.strip():
            return "execução bloqueada: timeframe do snapshot da decisão está indisponível"
        return None

    def _market_data_fingerprint_error(self, request: ExecutionRequest) -> str | None:
        expected = request.market_data_fingerprint
        if expected is None:
            return None
        provider = self._market_data_fingerprint_provider
        if provider is None:
            return "execução bloqueada: identidade dos dados de mercado não está vinculada ao runtime operacional"
        try:
            current = provider()
        except Exception as exc:
            return f"execução bloqueada: identidade dos dados de mercado indisponível: {type(exc).__name__}"
        if current is None:
            return "execução bloqueada: runtime não possui snapshot de mercado validado"
        if current != expected:
            return "execução bloqueada: dados de mercado mudaram desde a decisão; nova avaliação obrigatória"
        return None

    def _final_safety_barrier(self, *, now: datetime) -> str | None:
        incident_error = self._incident_error()
        if incident_error is not None:
            return incident_error
        refresh_error = self._refresh_kill_switch()
        if refresh_error is not None:
            return refresh_error
        if not self._kill_switch.allows_execution():
            return f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}"
        if self._maintenance is not None and self._maintenance.execution_blocked(now=now):
            return "execução bloqueada durante manutenção ativa do ecossistema."
        return self._global_barrier_error()

    def _abandon_reserved_request(self, request_id: str) -> None:
        if self._ledger is None:
            return
        try:
            current = self._ledger.status(request_id)
            if current is ExecutionLedgerStatus.RESERVED:
                self._ledger.mark_unknown(request_id)
        except (OSError, ValueError):
            pass

    def execute(self, request_id: str, request: ExecutionRequest, *, snapshot: DecisionSnapshot | None = None, timestamp: datetime | None = None, entry_conditions: tuple[str, ...] = ()) -> GatewayResult:
        validation_error = self._validate(request_id, request)
        if validation_error is not None:
            return GatewayResult(GatewayStatus.INVALID_REQUEST, validation_error)
        event_time = timestamp or datetime.now(timezone.utc)
        freshness_error = self._decision_freshness_error(created_at=event_time)
        if freshness_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, freshness_error)
        preflight_incident_error = self._incident_error()
        if preflight_incident_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, preflight_incident_error)
        barrier_error = self._global_barrier_error()
        if barrier_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, barrier_error)
        snapshot_error = self._decision_snapshot_error(request, snapshot)
        if snapshot_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, snapshot_error)
        market_data_error = self._market_data_fingerprint_error(request)
        if market_data_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, market_data_error)
        if self._maintenance is not None and self._maintenance.execution_blocked(now=event_time):
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada durante manutenção ativa do ecossistema.")
        audit_record = None
        if snapshot is not None and self._recorder is not None:
            audit_record = self._recorder.record_decision(snapshot, timestamp=event_time)
        refresh_error = self._refresh_kill_switch()
        if refresh_error is not None:
            return GatewayResult(GatewayStatus.BLOCKED, refresh_error)
        if not self._kill_switch.allows_execution():
            return GatewayResult(GatewayStatus.BLOCKED, f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}")
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
        final_freshness_error = self._decision_freshness_error(created_at=event_time)
        if final_freshness_error is not None:
            self._mark_unknown(request_id, event_time, f"decisão expirou antes do dispatch: {final_freshness_error}")
            return GatewayResult(GatewayStatus.BLOCKED, final_freshness_error)
        final_snapshot_error = self._decision_snapshot_error(request, snapshot)
        if final_snapshot_error is not None:
            self._mark_unknown(request_id, event_time, f"snapshot da decisão mudou ou deixou de estar disponível: {final_snapshot_error}")
            return GatewayResult(GatewayStatus.BLOCKED, final_snapshot_error)
        final_market_data_error = self._market_data_fingerprint_error(request)
        if final_market_data_error is not None:
            self._mark_unknown(request_id, event_time, f"identidade de mercado mudou antes do dispatch: {final_market_data_error}")
            return GatewayResult(GatewayStatus.BLOCKED, final_market_data_error)
        try:
            result = self._executor.execute(request)
        except Exception as exc:
            self._mark_unknown(request_id, event_time, f"resultado do executor é incerto: {type(exc).__name__}: {exc}")
            self._open_incident_on_executor_failure(exc)
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"executor falhou; resultado marcado como UNKNOWN: {type(exc).__name__}: {exc}")
        if not isinstance(result, ExecutionResult):
            self._mark_unknown(request_id, event_time, "executor retornou resultado inválido")
            self._open_incident_on_executor_failure("resultado inválido")
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
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"execução aceita, mas persistência do ciclo falhou: {exc}", result)
        self._processed_request_ids.add(request_id)
        recorded_operation = None
        if snapshot is not None and self._recorder is not None:
            recorded_operation = self._recorder.record_operation(snapshot, timestamp=event_time, entry_conditions=entry_conditions, audit_record=audit_record)
        return GatewayResult(GatewayStatus.ACCEPTED, result.message, result, recorded_operation)

    def _open_incident_on_executor_failure(self, error: object) -> None:
        if self._incident_manager is None:
            return
        try:
            self._incident_manager.open_incident(title="Falha técnica no executor", message=f"O executor apresentou uma falha e novas operações foram bloqueadas: {error}")
        except Exception:
            pass

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
        if request.market_data_fingerprint is not None and (not isinstance(request.market_data_fingerprint, str) or len(request.market_data_fingerprint) != 64):
            return "identidade dos dados de mercado inválida."
        return None
