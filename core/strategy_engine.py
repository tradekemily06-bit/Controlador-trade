from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .models import AnalysisResult
from .advanced_filters import AdvancedFilters
from .scoring import calculate_score
from .signal_engine import SignalEngine


@dataclass(frozen=True)
class StrategyInput:
    trend: float
    pressure: float
    structure: float
    rejection: float
    volume: float
    confirmation: float
    confirmed: bool
    filters_ok: bool = False
    symbol: str | None = None
    timeframe: str | None = None


class StrategyEngine:
    """Orquestra os componentes técnicos do motor de estratégia.

    O StrategyEngine calcula o score ponderado e delega a decisão
    COMPRA/VENDA/AGUARDAR ao SignalEngine. Não conhece corretora,
    execução ou gerenciamento de risco.
    """

    def __init__(self, signal_engine: SignalEngine | None = None) -> None:
        self.signal_engine = signal_engine or SignalEngine()

    def evaluate(self, data: StrategyInput) -> AnalysisResult:
        if not isinstance(data.confirmed, bool):
            raise ValueError("confirmed deve ser booleano.")

        if not isinstance(data.filters_ok, bool):
            raise ValueError("filters_ok deve ser booleano.")

        values = {
            "trend": data.trend,
            "pressure": data.pressure,
            "structure": data.structure,
            "rejection": data.rejection,
            "volume": data.volume,
            "confirmation": data.confirmation,
        }

        for name, value in values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{name} deve ser numérico e finito.")
            if not 0 <= value <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100.")

        score = calculate_score(**values)
        filter_result = AdvancedFilters().evaluate(**values)
        effective_filters_ok = data.filters_ok is True and filter_result.allowed

        result = self.signal_engine.evaluate(
            score=score,
            confirmed=data.confirmed,
            filters_ok=effective_filters_ok,
            symbol=data.symbol,
            timeframe=data.timeframe,
        )
        if not filter_result.allowed:
            # A caller-supplied filters_ok=True is never proof that the market
            # filters passed; the internal deterministic filter result is required.
            return AnalysisResult(
                signal=result.signal,
                score=result.score,
                reason="Filtros bloqueados: " + "; ".join(filter_result.reasons),
                confirmed=result.confirmed,
                symbol=result.symbol,
                timeframe=result.timeframe,
            )
        return result
