from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from core.models import Signal


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
        direction: Signal,
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

        if direction not in (Signal.COMPRA, Signal.VENDA):
            return FilterResult(False, ("Direção de entrada inválida.",))

        # A confirmação técnica deve vir dos dados do ciclo, não apenas do
        # booleano enviado pelo cliente.
        if confirmation < 100:
            reasons.append("Confirmação insuficiente.")

        # Os mesmos filtros são aplicados de forma simétrica à direção:
        # scores altos indicam pressão/tendência compradora; baixos, vendedora.
        if direction is Signal.COMPRA:
            if trend < 50:
                reasons.append("Tendência insuficiente para compra.")
            if structure < 50:
                reasons.append("Estrutura insuficiente para compra.")
            if pressure < 50:
                reasons.append("Pressão insuficiente para compra.")
            if volume < 40:
                reasons.append("Volume insuficiente para compra.")
            if rejection < 20:
                reasons.append("Rejeição fraca para compra.")
        else:
            if trend > 50:
                reasons.append("Tendência insuficiente para venda.")
            if structure > 50:
                reasons.append("Estrutura insuficiente para venda.")
            if pressure > 50:
                reasons.append("Pressão insuficiente para venda.")
            if volume > 60:
                reasons.append("Volume insuficiente para venda.")
            if rejection > 80:
                reasons.append("Rejeição fraca para venda.")

        return FilterResult(
            allowed=not reasons,
            reasons=tuple(reasons),
        )


def evaluate_advanced_filters(**kwargs: float) -> FilterResult:
    return AdvancedFilters().evaluate(**kwargs)
