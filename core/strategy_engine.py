from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .models import AnalysisResult
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
    filters_ok: bool = True
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

        return self.signal_engine.evaluate(
            score=score,
            confirmed=data.confirmed,
            filters_ok=data.filters_ok,
            symbol=data.symbol,
            timeframe=data.timeframe,
        )
