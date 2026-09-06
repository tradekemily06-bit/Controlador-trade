from dataclasses import dataclass

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
    """Orquestra sinal e gerenciamento de risco."""

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager

    def evaluate(
        self,
        *,
        analysis: AnalysisResult,
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
            reason="Sinal aprovado e risco dentro dos limites.",
        )
