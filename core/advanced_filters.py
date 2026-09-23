from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FilterResult:
    """Resultado determinístico dos filtros de qualidade da estratégia."""

    allowed: bool
    reasons: tuple[str, ...]


class AdvancedFilters:
    """Aplica filtros adicionais sem conhecer execução ou corretora."""

    def evaluate(
        self,
        *,
        trend: float,
        pressure: float,
        structure: float,
        rejection: float,
        volume: float,
        confirmation: float,
        direction: str | None = None,
    ) -> FilterResult:
        """Avalia alinhamento na direção candidata, sem confundir BUY com SELL."""
        values = {
            "trend": trend,
            "pressure": pressure,
            "structure": structure,
            "rejection": rejection,
            "volume": volume,
            "confirmation": confirmation,
        }

        reasons: list[str] = []
        for name, value in values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0 <= value <= 100
            ):
                return FilterResult(False, (f"{name} inválido.",))

        if confirmation < 100:
            reasons.append("Confirmação insuficiente.")

        if direction not in {"BUY", "SELL"}:
            # Um filtro não pode transformar alinhamento em direção por conta própria.
            # Sem direção candidata explícita, o resultado nunca é acionável.
            reasons.append("Sem direção candidata suficientemente definida.")
        else:
            oriented = {
                "BUY": {
                    "trend": trend,
                    "pressure": pressure,
                    "structure": structure,
                    "rejection": rejection,
                    "volume": volume,
                },
                "SELL": {
                    "trend": 100 - trend,
                    "pressure": 100 - pressure,
                    "structure": 100 - structure,
                    "rejection": 100 - rejection,
                    "volume": 100 - volume,
                },
            }[direction]
            for name, value in oriented.items():
                if value < 50:
                    reasons.append(f"{name.capitalize()} não está alinhado com {direction}.")

        return FilterResult(allowed=not reasons, reasons=tuple(reasons))


def evaluate_advanced_filters(**kwargs: float) -> FilterResult:
    return AdvancedFilters().evaluate(**kwargs)
