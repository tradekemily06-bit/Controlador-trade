from dataclasses import dataclass

from .market_context import MarketContext, MarketContextResult, MarketDirection
from .models import AnalysisResult, Signal
from .operational_state import OperationalState
from .risk_manager import RiskManager
from .senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from .senior_operation_assessment import SeniorOperationDisposition
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

    Fail-closed: uma decisão EXECUTAR exige contexto sênior completo e, quando
    o ciclo foi produzido pela fronteira sênior atual, uma avaliação explícita
    de qualidade da oportunidade. Essa avaliação responde se a oportunidade
    realmente sobreviveu à revisão profissional; ela nunca concede autoridade
    de execução. Gates determinísticos anteriores continuam podendo explicar
    primeiro por que uma operação não é elegível.
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
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Estado operacional indisponível.")

        if not isinstance(operational_state, OperationalState):
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Estado operacional inválido.")

        if analysis.signal == Signal.AGUARDAR:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, analysis.reason)

        if market_context is None:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Contexto de mercado indisponível.")

        if market_context.context != MarketContext.FAVORAVEL:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Contexto de mercado não favorável para execução.")

        if analysis.signal == Signal.COMPRA and market_context.direction != MarketDirection.ALTA:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Direção do contexto incompatível com sinal de compra.")

        if analysis.signal == Signal.VENDA and market_context.direction != MarketDirection.BAIXA:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Direção do contexto incompatível com sinal de venda.")

        risk = self.risk_manager.evaluate(state=operational_state)
        if not risk.allowed:
            return DecisionResult(FinalDecision.BLOQUEAR, analysis.signal, risk.reason)

        if senior_context is None:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Contexto sênior obrigatório antes de qualquer decisão de execução.")

        if not isinstance(senior_context, SeniorContextCycle):
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Contexto sênior inválido.")

        if senior_context.execution_authorized:
            return DecisionResult(FinalDecision.BLOQUEAR, analysis.signal, "O ciclo sênior não pode conceder autoridade de execução.")

        if senior_context.quality is not SeniorContextQuality.COMPLETE:
            return DecisionResult(FinalDecision.AGUARDAR, analysis.signal, "Contexto sênior incompleto ou requer reavaliação.")

        # New senior cycles carry an explicit opportunity-quality judgment.
        # Legacy synthetic contexts without it remain compatible here, while
        # every production cycle assembled by SeniorContextCycleBoundary has it.
        operation_assessment = senior_context.operation_assessment
        if operation_assessment is not None:
            if operation_assessment.execution_authorized:
                return DecisionResult(FinalDecision.BLOQUEAR, analysis.signal, "A avaliação de oportunidade sênior não pode conceder autoridade de execução.")
            if operation_assessment.disposition is not SeniorOperationDisposition.SUITABLE:
                return DecisionResult(
                    FinalDecision.AGUARDAR,
                    analysis.signal,
                    f"Avaliação profissional da oportunidade: {operation_assessment.quality_level}. Reavaliação necessária antes de qualquer execução.",
                )

        senior_risk = self.senior_risk_gate.evaluate(
            senior_risk=senior_context.risk_assessment,
            operational_risk=risk,
        )
        if not senior_risk.allowed:
            return DecisionResult(FinalDecision.BLOQUEAR, analysis.signal, senior_risk.reason)

        return DecisionResult(
            FinalDecision.EXECUTAR,
            analysis.signal,
            "Sinal, contexto sênior, avaliação profissional da oportunidade, contexto de mercado, estado operacional e risco sênior/operacional aprovados.",
        )
