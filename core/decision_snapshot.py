from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .decision_engine import DecisionResult
from .market_context import MarketContextResult
from .models import AnalysisResult
from .operational_state import OperationalState
from .signal_quality import SignalQuality


@dataclass(frozen=True)
class DecisionSnapshot:
    """Registro imutável e explicável dos fatores de uma decisão."""

    signal: str
    analysis_score: float
    confirmed: bool
    quality_score: float
    quality_level: str
    actionable: bool
    decision: str
    decision_reason: str
    market_context: str | None
    market_direction: str | None
    market_score: float | None
    operational_state_available: bool
    trades_today: int | None
    consecutive_losses: int | None
    symbol: str | None
    timeframe: str | None

    @classmethod
    def from_results(
        cls,
        *,
        analysis: AnalysisResult,
        quality: SignalQuality,
        decision: DecisionResult,
        market_context: MarketContextResult | None,
        operational_state: OperationalState | None,
    ) -> "DecisionSnapshot":
        return cls(
            signal=analysis.signal.value,
            analysis_score=analysis.score,
            confirmed=analysis.confirmed,
            quality_score=quality.score,
            quality_level=quality.level.value,
            actionable=quality.actionable,
            decision=decision.decision,
            decision_reason=decision.reason,
            market_context=(
                market_context.context.value if market_context is not None else None
            ),
            market_direction=(
                market_context.direction.value if market_context is not None else None
            ),
            market_score=(
                market_context.score if market_context is not None else None
            ),
            operational_state_available=operational_state is not None,
            trades_today=(
                operational_state.trades_today
                if operational_state is not None
                else None
            ),
            consecutive_losses=(
                operational_state.consecutive_losses
                if operational_state is not None
                else None
            ),
            symbol=analysis.symbol,
            timeframe=analysis.timeframe,
        )

    def explain(self) -> str:
        """Retorna uma explicação humana, determinística e auditável."""
        context = self.market_context or "INDISPONÍVEL"
        direction = self.market_direction or "INDISPONÍVEL"
        return (
            f"Sinal={self.signal}; score={self.analysis_score:.2f}; "
            f"confirmado={self.confirmed}; qualidade={self.quality_level} "
            f"({self.quality_score:.2f}); decisão={self.decision}; "
            f"contexto={context}; direção={direction}; "
            f"risco_estado_disponível={self.operational_state_available}; "
            f"motivo={self.decision_reason}"
        )

    def as_dict(self) -> dict[str, Any]:
        """Converte o snapshot para dados simples, adequados à auditoria."""
        return {
            "signal": self.signal,
            "analysis_score": self.analysis_score,
            "confirmed": self.confirmed,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level,
            "actionable": self.actionable,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "market_context": self.market_context,
            "market_direction": self.market_direction,
            "market_score": self.market_score,
            "operational_state_available": self.operational_state_available,
            "trades_today": self.trades_today,
            "consecutive_losses": self.consecutive_losses,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
