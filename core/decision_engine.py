from dataclasses import dataclass

from .market_context import MarketContext, MarketContextResult, MarketDirection
from .models import AnalysisResult, Signal
from .operational_state import OperationalState
from .risk_manager import RiskManager


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
    Orquestra sinal, contexto de mercado, estado operacional e risco.

    Fail-closed: EXECUTAR só é possível quando todas as condições
    obrigatórias estão explicitamente aprovadas.
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager

    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
        market_context: MarketContextResult | None = None,
        operational_state: OperationalState | None = None,
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

        risk = self.risk_manager.evaluate(
            state=operational_state,
        )

        if not risk.allowed:
            return DecisionResult(
                decision=FinalDecision.BLOQUEAR,
                signal=analysis.signal,
                reason=risk.reason,
            )

        return DecisionResult(
            decision=FinalDecision.EXECUTAR,
            signal=analysis.signal,
            reason="Sinal, contexto, estado operacional e risco aprovados.",
        )
