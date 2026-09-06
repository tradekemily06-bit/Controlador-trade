from dataclasses import dataclass

from .market_context import MarketContext, MarketContextResult, MarketDirection
from .models import AnalysisResult, Signal
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
    """Orquestra sinal, contexto de mercado e gerenciamento de risco."""

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager

    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
        market_context: MarketContextResult | None = None,
        daily_result=0.0,
        operations_count=0,
        consecutive_losses=0,
    ) -> DecisionResult:

        if analysis.signal == Signal.AGUARDAR:
            return DecisionResult(
                decision=FinalDecision.AGUARDAR,
                signal=analysis.signal,
                reason=analysis.reason,
            )

        if market_context is not None:
            if market_context.context != MarketContext.FAVORAVEL:
                return DecisionResult(
                    decision=FinalDecision.AGUARDAR,
                    signal=analysis.signal,
                    reason=(
                        "Contexto de mercado não favorável "
                        "para execução."
                    ),
                )

            if (
                analysis.signal == Signal.COMPRA
                and market_context.direction != MarketDirection.ALTA
            ):
                return DecisionResult(
                    decision=FinalDecision.AGUARDAR,
                    signal=analysis.signal,
                    reason=(
                        "Direção do contexto incompatível "
                        "com sinal de compra."
                    ),
                )

            if (
                analysis.signal == Signal.VENDA
                and market_context.direction != MarketDirection.BAIXA
            ):
                return DecisionResult(
                    decision=FinalDecision.AGUARDAR,
                    signal=analysis.signal,
                    reason=(
                        "Direção do contexto incompatível "
                        "com sinal de venda."
                    ),
                )

        risk = self.risk_manager.evaluate(
            daily_result=daily_result,
            operations_count=operations_count,
            consecutive_losses=consecutive_losses,
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
            reason="Sinal, contexto e risco aprovados.",
        )
