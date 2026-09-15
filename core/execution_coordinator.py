from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json

from core.decision_engine import FinalDecision
from core.execution_intent import ExecutionIntent
from core.execution_intent_admission import ExecutionIntentAdmission
from core.live_orchestrator import OrchestrationResult
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayResult, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest


def _canonical_value(value):
    """Convert decision inputs to deterministic JSON-safe values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _decision_identity(orchestration: OrchestrationResult) -> str:
    """Deterministic identity for the exact decision context used by a plan."""
    payload = {
        "signal": orchestration.analysis.signal,
        "score": orchestration.analysis.score,
        "reason": orchestration.analysis.reason,
        "confirmed": orchestration.analysis.confirmed,
        "symbol": orchestration.analysis.symbol,
        "timeframe": orchestration.analysis.timeframe,
        "quality_score": orchestration.quality.score,
        "quality_level": orchestration.quality.level,
        "actionable": orchestration.quality.actionable,
        "decision": orchestration.decision.decision,
        "decision_signal": orchestration.decision.signal,
        "decision_reason": orchestration.decision.reason,
        "snapshot": orchestration.snapshot.as_dict(),
        "senior_context": orchestration.senior_context,
        "timestamp": orchestration.timestamp.isoformat(),
    }
    canonical = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionPlan:
    """Plano explícito de execução derivado de uma decisão já avaliada."""

    request_id: str
    request: ExecutionRequest
    decision_identity: str
    entry_conditions: tuple[str, ...] = ()


class ExecutionCoordinator:
    """Liga a decisão à admissão de execução sem criar uma nova estratégia."""

    def __init__(self, gateway: ExecutionGateway) -> None:
        if gateway is None:
            raise ValueError("gateway é obrigatório.")
        self.gateway = gateway

    @staticmethod
    def build_plan(
        orchestration: OrchestrationResult,
        *,
        request_id: str,
        amount: float,
        duration_seconds: int,
        mode: ExecutionMode = ExecutionMode.DEMO,
        entry_conditions: tuple[str, ...] = (),
    ) -> ExecutionPlan:
        if not isinstance(orchestration, OrchestrationResult):
            raise ValueError("resultado de orquestração inválido.")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        if orchestration.decision.decision is not FinalDecision.EXECUTAR:
            raise ValueError("somente decisões EXECUTAR podem gerar plano de execução.")
        if mode is not ExecutionMode.DEMO:
            raise ValueError("somente execução DEMO é permitida pelo coordinator nesta etapa.")
        if orchestration.senior_context is None:
            raise ValueError("contexto sênior obrigatório antes de criar plano de execução.")
        if not isinstance(entry_conditions, tuple) or not all(isinstance(item, str) for item in entry_conditions):
            raise ValueError("entry_conditions deve ser uma tupla de strings.")
        signal = Signal(orchestration.analysis.signal.value)
        symbol = orchestration.analysis.symbol
        if not symbol:
            raise ValueError("decisão executável precisa de símbolo.")
        fingerprint = orchestration.market_data.fingerprint
        return ExecutionPlan(
            request_id=request_id,
            request=ExecutionRequest(
                symbol=symbol,
                signal=signal,
                amount=amount,
                duration_seconds=duration_seconds,
                mode=mode,
                request_id=request_id,
                market_data_fingerprint=fingerprint,
                risk_state_fingerprint=orchestration.snapshot.risk_state_fingerprint,
            ),
            decision_identity=_decision_identity(orchestration),
            entry_conditions=entry_conditions,
        )

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        orchestration: OrchestrationResult,
        entry_conditions: tuple[str, ...] | None = None,
    ) -> GatewayResult:
        if not isinstance(plan, ExecutionPlan):
            return GatewayResult(GatewayStatus.INVALID_REQUEST, "plano de execução inválido.")
        if not isinstance(orchestration, OrchestrationResult):
            return GatewayResult(GatewayStatus.INVALID_REQUEST, "resultado de orquestração inválido.")
        if orchestration.decision.decision is not FinalDecision.EXECUTAR:
            return GatewayResult(GatewayStatus.BLOCKED, "somente decisões EXECUTAR podem alcançar o gateway.")
        if orchestration.senior_context is None:
            return GatewayResult(GatewayStatus.BLOCKED, "contexto sênior obrigatório antes da admissão da execução.")
        if plan.request.market_data_fingerprint != orchestration.market_data.fingerprint:
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: plano não corresponde aos dados de mercado que originaram a decisão.")
        if plan.request.risk_state_fingerprint != orchestration.snapshot.risk_state_fingerprint:
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: plano não corresponde ao estado de risco que originou a decisão.")
        if plan.decision_identity != _decision_identity(orchestration):
            return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: decisão/orquestração mudou desde a criação do plano.")
        if entry_conditions is not None:
            if not isinstance(entry_conditions, tuple) or not all(isinstance(item, str) for item in entry_conditions):
                return GatewayResult(GatewayStatus.INVALID_REQUEST, "condições de entrada inválidas.")
            if entry_conditions != plan.entry_conditions:
                return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: condições de entrada mudaram desde a criação do plano.")
        intent = ExecutionIntent(
            request_id=plan.request_id,
            symbol=plan.request.symbol,
            signal=plan.request.signal,
            amount=plan.request.amount,
            duration_seconds=plan.request.duration_seconds,
            mode=plan.request.mode,
            created_at=orchestration.timestamp,
            market_data_fingerprint=orchestration.market_data.fingerprint,
            risk_state_fingerprint=orchestration.snapshot.risk_state_fingerprint,
        )
        return ExecutionIntentAdmission(self.gateway).admit(
            intent,
            senior_context=orchestration.senior_context,
            snapshot=orchestration.snapshot,
            entry_conditions=plan.entry_conditions,
        )
