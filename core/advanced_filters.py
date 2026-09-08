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
    ) -> FilterResult:
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
                return FilterResult(
                    allowed=False,
                    reasons=(f"{name} inválido.",),
                )

        # Sem confirmação, não há entrada válida.
        if confirmation < 100:
            reasons.append("Confirmação insuficiente.")

        # Exige alinhamento mínimo dos componentes principais.
        if trend < 50:
            reasons.append("Tendência insuficiente.")
        if structure < 50:
            reasons.append("Estrutura insuficiente.")
        if pressure < 50:
            reasons.append("Pressão insuficiente.")
        if volume < 40:
            reasons.append("Volume insuficiente.")

        # Rejeição muito baixa não bloqueia sozinha, pois pode haver
        # oportunidades válidas sem rejeição forte.
        if rejection < 20:
            reasons.append("Rejeição fraca.")

        return FilterResult(
            allowed=not reasons,
            reasons=tuple(reasons),
        )


def evaluate_advanced_filters(**kwargs: float) -> FilterResult:
    return AdvancedFilters().evaluate(**kwargs)
