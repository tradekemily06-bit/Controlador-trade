from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
from enum import Enum
from typing import Callable

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.ecosystem_maintenance import MaintenanceManager
from core.ecosystem_incidents import EcosystemIncidentManager
from core.file_lock import exclusive_file_lock
from core.global_operational_barrier import GlobalOperationalBarrier
from core.kill_switch import KillSwitch
from core.models import Signal
from core.operational_safety_store import OperationalSafetyStore
from core.p4_operational_recorder import P4OperationalRecorder, RecordedOperation
from core.risk_state_fingerprint import risk_state_identity
from core.risk_state_provider import RiskStateProvider, read_authoritative_risk_state
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
        risk_state_provider: RiskStateProvider | None = None,
        operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
        decision_freshness_policy: DecisionFreshnessPolicy | None = None,
    ) -> None:
        if executor is None:
            raise ValueError("executor é obrigatório.")
        if kill_switch is None:
            raise ValueError("kill_switch é obrigatório.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise ValueError("safety_store inválido.")
        if incident_manager is not None and not isinstance(incident_manager, EcosystemIncidentManager):
            raise ValueError("incident_manager inválido.")
        if risk_state_provider is not None and not isinstance(risk_state_provider, RiskStateProvider):
            raise ValueError("risk_state_provider inválido.")
        if operational_barrier_provider is not None and not callable(operational_barrier_provider):
            raise ValueError("operational_barrier_provider inválido.")
        if decision_freshness_policy is not None and not isinstance(decision_freshness_policy, DecisionFreshnessPolicy):
            raise ValueError("decision_freshness_policy inválida.")
        self._executor = executor
        self._kill_switch = kill_switch
        self._recorder = recorder
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._maintenance = maintenance
        self._safety_store = safety_store
        self._incident_manager = incident_manager
        self._risk_state_provider = risk_state_provider
        self._operational_barrier_provider = operational_barrier_provider
        self._operational_barrier_provider_locked = operational_barrier_provider is not None
        self._decision_freshness_policy = decision_freshness_policy
        self._decision_freshness_policy_locked = decision_freshness_policy is not None
        self._processed_request_ids: set[str] = set(ledger.records()) if ledger else set()
        self._dispatch_lock_path = ledger.path.with_name(f".{ledger.path.name}.dispatch.lock") if ledger is not None else None

    def set_operational_barrier_provider(
        self, provider: Callable[[], GlobalOperationalBarrier] | None
    ) -> None:
        """Bind the barrier once; an established provider cannot be replaced or removed."""
        if self._operational_barrier_provider_locked:
            raise RuntimeError("barreira operacional já está vinculada e não pode ser substituída")
        if provider is not None and not callable(provider):
            raise ValueError("operational_barrier_provider inválido.")
        self._operational_barrier_provider = provider
        if provider is not None:
            self._operational_barrier_provider_locked = True

    def set_decision_freshness_policy(self, policy: DecisionFreshnessPolicy | None) -> None:
        """Bind freshness policy once; consolidated runtime policy cannot be disabled later."""
        if self._decision_freshness_policy_locked:
            raise RuntimeError("política de frescor da decisão já está vinculada e não pode ser substituída")
        if policy is not None and not isinstance(policy, DecisionFreshnessPolicy):
            raise ValueError("decision_freshness_policy inválida.")
        self._decision_freshness_policy = policy
        if policy is not None:
            self._decision_freshness_policy_locked = True

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        return type(exc).__name__

    def _refresh_kill_switch(self) -> str | None:
        if self._safety_store is None:
            return None
        try:
            _audit, persisted = self._safety_store.load()
            self._kill_switch.synchronize(persisted.state)
            return None
        except (OSError, ValueError, TypeError) as exc:
            return f"estado de segurança indisponível: {self._safe_error(exc)}"

    def _global_barrier(self) -> str | None:
        if self._operational_barrier_provider is None:
            return None
        try:
            barrier = self._operational_barrier_provider()
            if not isinstance(barrier, GlobalOperationalBarrier):
                return "barreira operacional indisponível; tipo inválido"
            decision = barrier.evaluate()
        except Exception as exc:
            return f"barreira operacional indisponível: {self._safe_error(exc)}"
        if not decision.operationally_allowed:
            return f"ecossistema bloqueado: {decision.reason}"
        return None

    def _decision_freshness_barrier(self, snapshot: DecisionSnapshot | None, *, now: datetime) -> str | None:
        if self._decision_freshness_policy is None:
            return None
        if snapshot is None or snapshot.created_at is None:
            return "timestamp da decisão ausente; nova análise obrigatória antes do dispatch."
        return self._decision_freshness_policy.validate(snapshot.created_at, now=now)

    def _risk_state_barrier(self, snapshot: DecisionSnapshot | None) -> str | None:
        if self._risk_state_provider is None:
            return None
        if snapshot is None or not snapshot.risk_state_identity:
            return "identidade de risco da decisão indisponível; dispatch bloqueado."
        try:
            current = read_authoritative_risk_state(self._risk_state_provider)
            current_identity = risk_state_identity(current)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return f"estado de risco indisponível; dispatch bloqueado: {self._safe_error(exc)}"
        if current_identity != snapshot.risk_state_identity:
            return "estado de risco mudou desde a decisão; dispatch bloqueado para revalidação."
        return None

    def _final_safety_barrier(self, *, now: datetime, snapshot: DecisionSnapshot | None) -> str | None:
        global_error = self._global_barrier()
        if global_error is not None:
            return global_error
        refresh_error = self._refresh_kill_switch()
        if refresh_error is not None:
            return refresh_error
        if not self._kill_switch.allows_execution():
            return f"execução bloqueada pelo kill switch: {self._kill_switch.state.reason}"
        if self._maintenance is not None and self._maintenance.execution_blocked(now=now):
            return "execução bloqueada durante manutenção ativa do ecossistema."
        if self._incident_manager is not None and self._incident_manager.execution_blocked():
            return "execução bloqueada por incidente técnico ativo."
        freshness_error = self._decision_freshness_barrier(snapshot, now=now)
        if freshness_error is not None:
            return freshness_error
        return self._risk_state_barrier(snapshot)

    def _request_for_dispatch(self, request: ExecutionRequest, snapshot: DecisionSnapshot | None) -> ExecutionRequest:
        if snapshot is None or snapshot.risk_state_identity is None:
            return request
        if request.risk_state_fingerprint not in (None, snapshot.risk_state_identity):
            raise ValueError("identidade de risco da requisição difere do snapshot; dispatch bloqueado.")
        return replace(request, risk_state_fingerprint=snapshot.risk_state_identity)

    def _dispatch_with_authoritative_barriers(
        self, request: ExecutionRequest, snapshot: DecisionSnapshot | None, *, now: datetime
    ) -> tuple[ExecutionResult | None, str | None]:
        """Serialize final authoritative checks with the actual executor call."""
        lock = exclusive_file_lock(self._dispatch_lock_path) if self._dispatch_lock_path is not None else nullcontext()
        with lock:
            final_safety_error = self._final_safety_barrier(now=now, snapshot=snapshot)
            if final_safety_error is not None:
                return None, final_safety_error
            try:
                effective_request = self._request_for_dispatch(request, snapshot)
            except ValueError:
                return None, "requisição incompatível com o snapshot; dispatch bloqueado."
            return self._executor.execute(effective_request), None

    def _abandon_reserved_request(self, request_id: str) -> None:
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
        # Caller timestamps are audit/event time, never authority over the live maintenance window.
        operational_now = datetime.now(timezone.utc)
        if self._maintenance is not None and self._maintenance.execution_blocked(now=operational_now):
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada durante manutenção ativa do ecossistema.")
        if self._incident_manager is not None and self._incident_manager.execution_blocked():
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada por incidente técnico ativo.")
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
            except (OSError, ValueError):
                current = self._ledger.status(request_id)
                if current is not None:
                    self._processed_request_ids.add(request_id)
                    if current in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                        return GatewayResult(GatewayStatus.BLOCKED, "request_id está em estado incerto; reconciliação explícita obrigatória antes de novo envio.")
                    return GatewayResult(GatewayStatus.DUPLICATE, "request_id já processado; execução duplicada recusada.")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "não foi possível reservar request_id com segurança")
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
            except (OSError, ValueError):
                self._abandon_reserved_request(request_id)
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "não foi possível persistir o início da execução")
        try:
            result, barrier_error = self._dispatch_with_authoritative_barriers(request, snapshot, now=operational_now)
        except Exception as exc:
            self._mark_unknown(request_id, event_time, "resultado do executor é incerto")
            if self._incident_manager is not None:
                try:
                    self._incident_manager.open_incident(title="Falha técnica na execução", message=f"O executor apresentou uma falha inesperada ({self._safe_error(exc)}). O resultado da ordem ficou UNKNOWN e novas ordens foram bloqueadas para investigação.")
                except (ValueError, RuntimeError):
                    pass
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, f"executor falhou; resultado marcado como UNKNOWN: {self._safe_error(exc)}")
        if barrier_error is not None:
            self._mark_pre_dispatch_block(request_id, event_time, barrier_error)
            return GatewayResult(GatewayStatus.BLOCKED, barrier_error)
        if not isinstance(result, ExecutionResult):
            self._mark_unknown(request_id, event_time, "executor retornou resultado inválido")
            if self._incident_manager is not None:
                try:
                    self._incident_manager.open_incident(title="Resposta técnica inválida", message="O executor retornou um formato inválido. O resultado da ordem ficou UNKNOWN e novas ordens foram bloqueadas para investigação.")
                except (ValueError, RuntimeError):
                    pass
            return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "executor retornou resultado inválido; execução marcada como UNKNOWN.")
        if not result.accepted:
            if self._ledger is not None:
                try:
                    self._ledger.mark_rejected(request_id)
                except (OSError, ValueError):
                    self._mark_unknown(request_id, event_time, "execução rejeitada, mas ledger não foi persistido")
                    return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "execução rejeitada, mas persistência falhou; estado UNKNOWN", result)
            if self._lifecycle is not None:
                try:
                    self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, event_time, result.message))
                except (OSError, ValueError):
                    return GatewayResult(
                        GatewayStatus.EXECUTOR_ERROR,
                        "execução rejeitada, mas persistência do ciclo falhou; recuperação/reconciliação obrigatória",
                        result,
                    )
            self._processed_request_ids.add(request_id)
            return GatewayResult(GatewayStatus.EXECUTION_REJECTED, result.message, result)
        if self._ledger is not None:
            try:
                self._ledger.mark_accepted(request_id)
            except (OSError, ValueError):
                self._mark_unknown(request_id, event_time, "execução aceita, mas ledger não foi persistido")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "execução aceita, mas ledger não foi persistido; estado UNKNOWN", result)
        if self._lifecycle is not None:
            try:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.ACCEPTED, event_time, result.message))
            except (OSError, ValueError):
                self._mark_unknown(request_id, event_time, "execução aceita, mas persistência do ciclo falhou")
                return GatewayResult(GatewayStatus.EXECUTOR_ERROR, "execução aceita, mas persistência do ciclo falhou; estado UNKNOWN", result)
        self._processed_request_ids.add(request_id)
        recorded_operation = None
        if snapshot is not None and self._recorder is not None:
            recorded_operation = self._recorder.record_operation(snapshot, timestamp=event_time, entry_conditions=entry_conditions, audit_record=audit_record)
        return GatewayResult(GatewayStatus.ACCEPTED, result.message, result, recorded_operation)

    def _mark_pre_dispatch_block(self, request_id: str, timestamp: datetime, message: str) -> None:
        """Persist a known pre-dispatch block; UNKNOWN is reserved for uncertain dispatch outcomes."""
        if self._ledger is not None:
            try:
                current_status = self._ledger.status(request_id)
                if current_status is ExecutionLedgerStatus.RESERVED:
                    self._ledger.mark_rejected(request_id)
            except (OSError, ValueError):
                pass
        if self._lifecycle is None:
            return
        try:
            current = self._lifecycle.get(request_id)
            if current is None:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, timestamp, message))
            elif current.state is ExecutionLifecycleState.PENDING:
                self._lifecycle.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.REJECTED, timestamp, message))
        except (OSError, ValueError):
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
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return "Símbolo não pode ser vazio."
        if isinstance(request.amount, bool) or not isinstance(request.amount, (int, float)) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return "Valor da execução deve ser um número finito positivo."
        if isinstance(request.duration_seconds, bool) or not isinstance(request.duration_seconds, int) or request.duration_seconds <= 0:
            return "Duração deve ser um inteiro positivo."
        if request.request_id is not None and request.request_id != request_id:
            return "request_id externo difere da identidade da requisição."
        return None
