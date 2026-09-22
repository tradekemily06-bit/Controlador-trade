from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from core.decision_snapshot import DecisionSnapshot
from core.file_lock import exclusive_file_lock
from core.global_operational_barrier import GlobalOperationalBarrier
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission
from core.p114_real_safety_gate import RealSafetyReport
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from core.real_safety_provider import RealSafetyProvider, read_authoritative_real_safety
from core.risk_state_fingerprint import risk_state_identity
from core.risk_state_provider import RiskStateProvider, read_authoritative_risk_state
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
    """Single REAL dispatch boundary with authoritative identity and safety checks."""

    def __init__(self, adapter_gateway: BrokerAdapterGateway, ledger: ExecutionLedger,
                 risk_state_provider: RiskStateProvider, real_safety_provider: RealSafetyProvider,
                 operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
                 reconciliation_evidence_verifier: BrokerReconciliationEvidenceAuthority | None = None) -> None:
        if not isinstance(adapter_gateway, BrokerAdapterGateway):
            raise ValueError("adapter_gateway inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger é obrigatório para execução REAL.")
        if not isinstance(risk_state_provider, RiskStateProvider):
            raise ValueError("risk_state_provider autoritativo é obrigatório para execução REAL.")
        if not isinstance(real_safety_provider, RealSafetyProvider):
            raise ValueError("real_safety_provider autoritativo é obrigatório para execução REAL.")
        if operational_barrier_provider is not None and not callable(operational_barrier_provider):
            raise ValueError("operational_barrier_provider inválido.")
        if reconciliation_evidence_verifier is not None and not isinstance(reconciliation_evidence_verifier, BrokerReconciliationEvidenceAuthority):
            raise ValueError("reconciliation_evidence_verifier deve ser uma autoridade de evidência REAL autorizada.")
        self._gateway = adapter_gateway
        self._ledger = ledger
        self._risk_state_provider = risk_state_provider
        self._real_safety_provider = real_safety_provider
        self._operational_barrier_provider = operational_barrier_provider
        self._reconciliation_evidence_verifier = reconciliation_evidence_verifier
        self._processed_request_ids: set[str] = set(ledger.records())
        self._dispatch_lock_path = ledger.path.with_name(f".{ledger.path.name}.dispatch.lock")
        self._dispatch_started = False
        self._reconciliation_started = False

    def set_operational_barrier_provider(self, provider: Callable[[], GlobalOperationalBarrier] | None) -> None:
        if self._dispatch_started or self._reconciliation_started:
            raise RuntimeError("barreira operacional REAL já foi vinculada ao ciclo de execução e não pode ser substituída")
        if provider is not None and not callable(provider):
            raise ValueError("operational_barrier_provider inválido.")
        if self._operational_barrier_provider is not None and provider is not self._operational_barrier_provider:
            raise RuntimeError("barreira operacional REAL já configurada; substituição não permitida")
        self._operational_barrier_provider = provider

    def set_reconciliation_evidence_verifier(self, verifier: BrokerReconciliationEvidenceAuthority | None) -> None:
        if self._dispatch_started or self._reconciliation_started:
            raise RuntimeError("autoridade de evidência REAL já foi usada e não pode ser substituída")
        if verifier is not None and not isinstance(verifier, BrokerReconciliationEvidenceAuthority):
            raise ValueError("reconciliation_evidence_verifier deve ser uma autoridade de evidência REAL autorizada.")
        if self._reconciliation_evidence_verifier is not None and verifier is not self._reconciliation_evidence_verifier:
            raise RuntimeError("autoridade de evidência REAL já configurada; substituição não permitida")
        self._reconciliation_evidence_verifier = verifier

    def _global_barrier_error(self) -> str | None:
        provider = self._operational_barrier_provider
        if provider is None:
            return "barreira operacional global não configurada; execução REAL bloqueada"
        try:
            barrier = provider()
            if not isinstance(barrier, GlobalOperationalBarrier):
                return "provedor da barreira operacional global retornou um objeto inválido"
            decision = barrier.evaluate()
        except Exception as exc:
            return f"estado da barreira operacional global indisponível: {type(exc).__name__}"
        if not decision.operationally_allowed:
            return f"barreira operacional global bloqueou REAL: {decision.reason}"
        return None

    def _global_barrier_revalidation(self) -> RealGatewayResult | None:
        error = self._global_barrier_error()
        if error is None:
            return None
        return RealGatewayResult(RealGatewayStatus.BLOCKED, error)

    @staticmethod
    def _valid_request(request: ExecutionRequest) -> bool:
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return False
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return False
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return False
        if not isinstance(request.amount, (int, float)) or not math.isfinite(request.amount) or request.amount <= 0:
            return False
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return False
        return True

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        return type(exc).__name__

    @staticmethod
    def _safe_execution_message(execution: ExecutionResult | None, fallback: str) -> str:
        if execution is None:
            return fallback
        message = execution.message
        if not isinstance(message, str) or not message.strip():
            return fallback
        return message.strip()[:256]

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    def _validate_context_binding(self, *, broker: str, request_id: str,
                                  request: ExecutionRequest,
                                  authorization: RealExecutionAuthorization,
                                  admission: RealAdmission) -> RealGatewayResult | None:
        """Require one immutable identity across authorization, admission and request."""
        normalized_broker = broker.strip().lower()
        normalized_symbol = self._normalize_symbol(request.symbol)
        normalized_request_id = request_id.strip()

        if authorization.request_id.strip() != normalized_request_id:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id da autorização REAL difere da requisição; dispatch bloqueado.")
        if admission.request_id.strip() != normalized_request_id:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id da admissão REAL difere da requisição; dispatch bloqueado.")
        if self._normalize_symbol(authorization.symbol) != normalized_symbol:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "símbolo da autorização REAL difere da requisição; dispatch bloqueado.")
        if self._normalize_symbol(admission.symbol) != normalized_symbol:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "símbolo da admissão REAL difere da requisição; dispatch bloqueado.")
        if authorization.broker_id.strip().lower() != normalized_broker:
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker da requisição difere da autorização.")
        if admission.broker_id.strip().lower() != normalized_broker:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "broker da requisição difere da admissão REAL.")
        if authorization.adapter_id.strip() != admission.adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "adapter_id da autorização difere da admissão REAL; dispatch bloqueado.")
        try:
            resolved_adapter_id = self._gateway.adapter_id(broker)
        except Exception as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"identidade do adapter REAL indisponível: {self._safe_error(exc)}")
        if resolved_adapter_id.strip() != authorization.adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "adapter_id autorizado não corresponde ao adapter resolvido pelo gateway; dispatch bloqueado.")
        if resolved_adapter_id.strip() != admission.adapter_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "adapter_id admitido não corresponde ao adapter resolvido pelo gateway; dispatch bloqueado.")
        return None

    def _revalidate_risk(self, snapshot: DecisionSnapshot) -> RealGatewayResult | None:
        if not isinstance(snapshot, DecisionSnapshot):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "snapshot de decisão inválido; REAL bloqueado.")
        identity = snapshot.risk_state_identity
        if not isinstance(identity, str) or not identity.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "identidade de risco da decisão está ausente; REAL bloqueado.")
        try:
            current_state = read_authoritative_risk_state(self._risk_state_provider)
            current_identity = risk_state_identity(current_state)
        except Exception as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"não foi possível revalidar o estado de risco antes do dispatch: {self._safe_error(exc)}")
        if current_identity != identity:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "estado de risco mudou desde a decisão; novo ciclo de decisão obrigatório antes do dispatch.")
        return None

    def _revalidate_safety(self, safety: RealSafetyReport) -> RealGatewayResult | None:
        if not isinstance(safety, RealSafetyReport):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "contexto de segurança REAL inválido.")
        try:
            current_safety = read_authoritative_real_safety(self._real_safety_provider)
        except Exception as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"não foi possível revalidar a segurança REAL antes do dispatch: {self._safe_error(exc)}")
        if not current_safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta no momento do dispatch.")
        if current_safety != safety:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "estado de segurança REAL mudou desde a admissão; novo ciclo de admissão obrigatório antes do dispatch.")
        return None

    def _dispatch_locked(self, broker: str, request_id: str, request: ExecutionRequest,
                         safety: RealSafetyReport, snapshot: DecisionSnapshot,
                         authorization: RealExecutionAuthorization,
                         admission: RealAdmission) -> RealGatewayResult:
        binding = self._validate_context_binding(
            broker=broker, request_id=request_id, request=request,
            authorization=authorization, admission=admission,
        )
        if binding is not None:
            return binding
        current_status = self._ledger.status(request_id)
        if current_status is not None:
            self._processed_request_ids.add(request_id)
            if current_status in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, "request_id está em estado incerto; reconciliação explícita obrigatória antes de qualquer novo envio.")
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id já processado; replay REAL recusado.")
        for revalidator in (lambda: self._revalidate_risk(snapshot), lambda: self._revalidate_safety(safety)):
            result = revalidator()
            if result is not None:
                return result
        try:
            self._ledger.reserve_real(request_id, broker_id=broker, symbol=request.symbol)
            self._processed_request_ids.add(request_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível reservar request_id com segurança: {self._safe_error(exc)}")
        for revalidator in (self._global_barrier_revalidation, lambda: self._revalidate_risk(snapshot), lambda: self._revalidate_safety(safety)):
            result = revalidator()
            if result is not None:
                try:
                    self._ledger.mark_rejected(request_id)
                except (OSError, ValueError):
                    # If rejection cannot be persisted, RESERVED remains durable and recovery stays fail-closed.
                    pass
                return result
        try:
            result = self._gateway.execute(broker, request)
        except Exception as exc:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto: {self._safe_error(exc)}")
        expected_adapter_id = authorization.adapter_id.strip()
        if result.adapter_id != expected_adapter_id:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "identidade do adapter mudou ou não pôde ser confirmada após o dispatch; reconciliação explícita necessária.", result.execution)
        if getattr(result, "uncertain", False):
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"resultado REAL incerto e persistência do estado falhou: {self._safe_error(exc)}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "adapter REAL foi acionado, mas o resultado terminal não pôde ser confirmado; reconciliação explícita necessária.", result.execution)
        if result.execution is None:
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError):
                pass
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "resultado REAL sem execução confirmável; reconciliação explícita necessária.")
        if not result.execution.accepted:
            try:
                self._ledger.mark_rejected(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem rejeitada, mas persistência do estado falhou: {self._safe_error(exc)}", result.execution)
            return RealGatewayResult(RealGatewayStatus.REJECTED, self._safe_execution_message(result.execution, "ordem REAL rejeitada."), result.execution)
        if not isinstance(result.execution.external_id, str) or not result.execution.external_id.strip():
            try:
                self._ledger.mark_unknown(request_id)
            except (OSError, ValueError) as exc:
                return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"aceite REAL sem external_id e persistência falhou: {self._safe_error(exc)}", result.execution)
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, "aceite REAL sem external_id; reconciliação explícita necessária.", result.execution)
        try:
            self._ledger.mark_accepted_real(request_id, external_id=result.execution.external_id)
        except (OSError, ValueError) as exc:
            return RealGatewayResult(RealGatewayStatus.UNKNOWN, f"ordem REAL aceita, mas persistência da identidade falhou: {self._safe_error(exc)}", result.execution)
        return RealGatewayResult(RealGatewayStatus.ADMITTED, self._safe_execution_message(result.execution, "ordem REAL aceita."), result.execution)

    def execute(self, *, broker: str, request_id: str, request: ExecutionRequest,
                authorization: RealExecutionAuthorization, admission: RealAdmission,
                safety: RealSafetyReport, snapshot: DecisionSnapshot) -> RealGatewayResult:
        self._dispatch_started = True
        if not isinstance(authorization, RealExecutionAuthorization) or not isinstance(admission, RealAdmission) or not isinstance(safety, RealSafetyReport):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "contexto REAL inválido.")
        if not isinstance(snapshot, DecisionSnapshot):
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "snapshot de decisão inválido; REAL bloqueado.")
        barrier_error = self._global_barrier_error()
        if barrier_error is not None:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, barrier_error)
        if not isinstance(request_id, str) or not request_id.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request_id inválido.")
        if not authorization.active:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "autorização REAL inativa.")
        if not admission.admitted:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "admissão REAL não autorizada.")
        if admission.audit_id.strip() != authorization.audit_id.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "auditoria da admissão REAL difere da autorização; novo ciclo obrigatório.")
        if not safety.ready:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "barreira de segurança REAL não está pronta.")
        if not self._valid_request(request):
            return RealGatewayResult(RealGatewayStatus.REJECTED, "request REAL inválido.")
        if request.request_id != request_id:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "request_id externo difere da identidade da requisição; dispatch REAL bloqueado.")
        if not isinstance(broker, str) or not broker.strip():
            return RealGatewayResult(RealGatewayStatus.REJECTED, "broker inválido.")
        binding = self._validate_context_binding(
            broker=broker, request_id=request_id, request=request,
            authorization=authorization, admission=admission,
        )
        if binding is not None:
            return binding
        snapshot_risk = snapshot.risk_state_identity
        if not isinstance(snapshot_risk, str) or not snapshot_risk.strip():
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "identidade de risco do snapshot está ausente; REAL bloqueado.")
        if not isinstance(request.risk_state_fingerprint, str) or request.risk_state_fingerprint != snapshot_risk:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, "identidade de risco da requisição difere do snapshot; REAL bloqueado.")
        try:
            with exclusive_file_lock(self._dispatch_lock_path):
                return self._dispatch_locked(
                    broker, request_id, request, safety, snapshot,
                    authorization, admission,
                )
        except OSError as exc:
            return RealGatewayResult(RealGatewayStatus.BLOCKED, f"não foi possível obter a barreira de dispatch REAL: {self._safe_error(exc)}")

    def reconcile_unknown(self, request_id: str, *, executed: bool) -> None:
        raise RuntimeError("reconciliação REAL sem evidência externa autoritativa está bloqueada; use reconcile_unknown_with_evidence")

    def reconcile_unknown_with_evidence(self, request_id: str, *, executed: bool,
                                        evidence_id: str, evidence_source: str) -> None:
        self._reconciliation_started = True
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise ValueError("evidência externa exige evidence_id")
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            raise ValueError("evidence_source da evidência externa é obrigatório")
        if not isinstance(executed, bool):
            raise ValueError("executed da reconciliação REAL deve ser booleano")
        verifier = self._reconciliation_evidence_verifier
        if verifier is None:
            raise RuntimeError("autoridade de evidência REAL não configurada; reconciliação bloqueada")
        try:
            with exclusive_file_lock(self._dispatch_lock_path):
                status = self._ledger.status(request_id)
                if status not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                    raise ValueError("request_id não está em estado incerto reconciliável.")
                context = self._ledger.execution_context(request_id)
                if context is None:
                    raise ValueError("identidade persistida da operação REAL está ausente; reconciliação bloqueada")
                context_broker = context.get("broker_id")
                context_symbol = context.get("symbol")
                if not isinstance(context_broker, str) or not context_broker.strip() or not isinstance(context_symbol, str) or not context_symbol.strip():
                    raise ValueError("identidade persistida da operação REAL está inválida; reconciliação bloqueada")
                persisted_external_id = context.get("external_id")
                if isinstance(persisted_external_id, str) and persisted_external_id.strip() and persisted_external_id.strip() != evidence_id.strip():
                    raise ValueError("evidence_id difere do external_id emitido pelo broker para esta operação")
                try:
                    verified = bool(verifier.verify(
                        request_id=request_id,
                        evidence_id=evidence_id.strip(),
                        evidence_source=evidence_source.strip(),
                        broker_id=context_broker.strip(),
                        symbol=context_symbol.strip(),
                        executed=executed,
                    ))
                except Exception as exc:
                    raise RuntimeError(f"autoridade de evidência REAL indisponível: {self._safe_error(exc)}") from exc
                if not verified:
                    raise ValueError("evidência externa não foi confirmada pela autoridade; estado permanece incerto")
                self._ledger.reconcile(request_id, executed=executed, evidence_id=evidence_id.strip(), evidence_source=evidence_source.strip())
        except OSError as exc:
            raise RuntimeError("não foi possível obter a barreira de reconciliação REAL") from exc
