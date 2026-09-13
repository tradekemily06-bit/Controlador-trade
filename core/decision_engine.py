from dataclasses import dataclass

from .market_context import MarketContext, MarketContextResult, MarketDirection
from .models import AnalysisResult, Signal
from .operational_state import OperationalState
from .risk_manager import RiskManager
from .senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from .senior_risk_gate import SeniorRiskGate


class FinalDecision(str):
    EXECUTAR = "EXECUTAR"
    BLOQUEAR = "BLOQUEAR"
    AGUARDAR = "AGUARDAR"


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    signal: Signal
    reason: str


class DecisionEngine:
    """
    Orquestra sinal, contexto de mercado, contexto sênior, estado operacional e risco.

    Fail-closed: uma decisão EXECUTAR exige contexto sênior completo. O
    contexto sênior não concede autoridade; ele apenas comprova que a leitura
    contextual obrigatória foi concluída antes dos gates finais de risco e
    execução. Gates determinísticos anteriores continuam podendo explicar
    primeiro por que uma operação não é elegível; isso preserva diagnóstico,
    auditoria e compatibilidade dos contratos legados sem abrir um bypass.
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self.senior_risk_gate = SeniorRiskGate()

    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
        market_context: MarketContextResult | None = None,
        operational_state: OperationalState | None = None,
        senior_context: SeniorContextCycle | None = None,
        daily_result=None,
        operations_count=None,
        consecutive_losses=None,
    ) -> DecisionResult:
        if operational_state is None:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Estado operacional indisponível.",
            )

        if not isinstance(operational_state, OperationalState):
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Estado operacional inválido.",
            )

        if analysis.signal == Signal.AGUARDAR:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason=analysis.reason,
            )

        if market_context is None:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Contexto de mercado indisponível.",
            )

        if market_context.context != MarketContext.FAVORAVEL:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Contexto de mercado não favorável para execução.",
            )

        if (
            analysis.signal == Signal.COMPRA
            and market_context.direction != MarketDirection.ALTA
        ):
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Direção do contexto incompatível com sinal de compra.",
            )

        if (
            analysis.signal == Signal.VENDA
            and market_context.direction != MarketDirection.BAIXA
        ):
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Direção do contexto incompatível com sinal de venda.",
            )

        # Operational risk is still evaluated independently. A risk block is
        # never converted into execution merely because senior context exists.
        risk = self.risk_manager.evaluate(state=operational_state)
        if not risk.allowed:
            return DecisionResult(
                decision=FinalDecision.BLOQUEAR,
                signal=analysis.signal,
                reason=risk.reason,
            )

        # At this point the legacy gates say the operation is otherwise
        # actionable. Only now may it reach the mandatory senior-context gate.
        # Missing/incomplete context therefore cannot bypass to EXECUTAR.
        if senior_context is None:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Contexto sênior obrigatório antes de qualquer decisão de execução.",
            )

        if not isinstance(senior_context, SeniorContextCycle):
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Contexto sênior inválido.",
            )

        if senior_context.execution_authorized:
            return DecisionResult(
                decision=FinalDecision.BLOQUEAR,
                signal=analysis.signal,
                reason="O ciclo sênior não pode conceder autoridade de execução.",
            )

        if senior_context.quality is not SeniorContextQuality.COMPLETE:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason="Contexto sênior incompleto ou requer reavaliação.",
            )

        senior_risk = self.senior_risk_gate.evaluate(
            senior_risk=senior_context.risk_assessment,
            operational_risk=risk,
        )
        if not senior_risk.allowed:
            return DecisionResult(
                decision=FinalDecision.BLOQUEAR,
                signal=analysis.signal,
                reason=senior_risk.reason,
            )

        return DecisionResult(
            decision=FinalDecision.EXECUTAR,
            signal=analysis.signal,
            reason="Sinal, contexto sênior, contexto de mercado, estado operacional e risco sênior/operacional aprovados.",
        )
