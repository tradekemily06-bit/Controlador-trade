from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from data.models import Candle
from .market_direction import MarketDirection
from .methodology_features import extract_candle_features


class TemporalPhase(str, Enum):
    HISTORICAL = "HISTORICAL"
    PRESENT = "PRESENT"
    SCENARIO = "SCENARIO"


@dataclass(frozen=True)
class TemporalObservation:
    phase: TemporalPhase
    statement: str
    direction: str = "NEUTRAL"
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("statement is required")
        if self.direction not in {"BUY", "SELL", "NEUTRAL"}:
            raise ValueError("invalid direction")


@dataclass(frozen=True)
class FutureScenario:
    scenario_id: str
    condition: str
    implication: str
    direction: str = "NEUTRAL"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.condition.strip() or not self.implication.strip():
            raise ValueError("scenario fields are required")
        if self.direction not in {"BUY", "SELL", "NEUTRAL"}:
            raise ValueError("invalid scenario direction")


@dataclass(frozen=True)
class TemporalMarketContext:
    historical: tuple[TemporalObservation, ...]
    present: tuple[TemporalObservation, ...]
    scenarios: tuple[FutureScenario, ...]
    context_summary: str
    uncertainty: tuple[str, ...]


class TemporalMarketContextEngine:
    """Relate market history, present state and conditional future scenarios.

    This is deliberately not a prediction engine and does not encode a catalogue
    of trading rules. The past is evidence, the present is the current state, and
    the future is represented only as conditional scenarios that can be revised
    when new candles arrive.
    """

    def analyze(self, candles: list[Candle]) -> TemporalMarketContext:
        if not candles:
            return TemporalMarketContext((), (), (), "Sem histórico suficiente para construir contexto temporal.", ("O histórico ainda não está disponível.",))

        historical: list[TemporalObservation] = []
        present: list[TemporalObservation] = []
        scenarios: list[FutureScenario] = []

        directions = [
            "BUY" if candle.close > candle.open else
            "SELL" if candle.close < candle.open else "NEUTRAL"
            for candle in candles
        ]
        historical_direction = self._dominant_direction(directions[:-1]) if len(candles) > 1 else "NEUTRAL"
        current_direction = directions[-1]

        if len(candles) > 1:
            historical.append(TemporalObservation(
                TemporalPhase.HISTORICAL,
                f"O histórico anterior mostra direção predominante {historical_direction}, sem tratar essa predominância como regra de entrada.",
                historical_direction,
                ("history_direction",),
            ))

            historical_high = max(c.high for c in candles[:-1])
            historical_low = min(c.low for c in candles[:-1])
            latest = candles[-1]
            if latest.high > historical_high:
                historical.append(TemporalObservation(
                    TemporalPhase.HISTORICAL,
                    "O presente ultrapassou a máxima observada no histórico anterior; isso muda o contexto e exige observar a resposta posterior.",
                    "BUY",
                    ("history_high_break",),
                ))
            if latest.low < historical_low:
                historical.append(TemporalObservation(
                    TemporalPhase.HISTORICAL,
                    "O presente ultrapassou a mínima observada no histórico anterior; isso muda o contexto e exige observar a resposta posterior.",
                    "SELL",
                    ("history_low_break",),
                ))

        latest = candles[-1]
        features = extract_candle_features(latest)
        present.append(TemporalObservation(
            TemporalPhase.PRESENT,
            "O estado presente é descrito pelo comportamento do candle atual e por sua relação com o histórico, não por um sinal isolado.",
            current_direction,
            ("present_candle",),
        ))

        if len(candles) > 1:
            previous = candles[-2]
            if current_direction == historical_direction and current_direction != "NEUTRAL":
                present.append(TemporalObservation(
                    TemporalPhase.PRESENT,
                    "O comportamento atual é compatível com a direção predominante anterior; é uma continuidade observada, não uma garantia futura.",
                    current_direction,
                    ("history_present_relation",),
                ))
            elif current_direction != historical_direction and historical_direction != "NEUTRAL":
                present.append(TemporalObservation(
                    TemporalPhase.PRESENT,
                    "O comportamento atual diverge da direção predominante anterior; isso caracteriza uma mudança que precisa de contexto adicional.",
                    current_direction,
                    ("history_present_transition",),
                ))

            if latest.close > previous.high:
                scenarios.append(FutureScenario(
                    "continuation_or_reassessment_up",
                    "Se o deslocamento acima da máxima anterior encontrar continuidade no comportamento seguinte",
                    "o cenário de continuidade ganha evidência; se a continuidade falhar, a leitura deve ser reavaliada.",
                    "BUY",
                ))
            elif latest.close < previous.low:
                scenarios.append(FutureScenario(
                    "continuation_or_reassessment_down",
                    "Se o deslocamento abaixo da mínima anterior encontrar continuidade no comportamento seguinte",
                    "o cenário de continuidade ganha evidência; se a continuidade falhar, a leitura deve ser reavaliada.",
                    "SELL",
                ))
            else:
                scenarios.append(FutureScenario(
                    "range_or_transition",
                    "Se o preço permanecer dentro da estrutura observada",
                    "o próximo comportamento pode esclarecer continuidade, transição ou rejeição; não há base para tratar o futuro como conhecido.",
                    "NEUTRAL",
                ))

        if features.wick_to_body_ratio is not None and features.wick_to_body_ratio > 1:
            scenarios.append(FutureScenario(
                "response_to_rejection",
                "Se o comportamento seguinte confirmar ou negar a rejeição sugerida pelo pavio dominante",
                "a interpretação do movimento atual deve ser atualizada com essa nova evidência.",
                "NEUTRAL",
            ))

        uncertainty = (
            "O futuro não é observado: ele só pode ser tratado como cenário condicional.",
            "O histórico pode explicar contexto, mas não garante repetição do comportamento.",
            "Novas evidências devem substituir ou confirmar a leitura atual por reavaliação.",
        )
        summary = (
            f"Contexto temporal construído a partir de {len(candles)} candles: "
            f"histórico={historical_direction}, presente={current_direction}, "
            f"cenários condicionais={len(scenarios)}."
        )
        return TemporalMarketContext(
            historical=tuple(historical),
            present=tuple(present),
            scenarios=tuple(scenarios),
            context_summary=summary,
            uncertainty=uncertainty,
        )

    @staticmethod
    def _dominant_direction(directions: list[str]) -> str:
        buys = directions.count("BUY")
        sells = directions.count("SELL")
        if buys == sells:
            return "NEUTRAL"
        return "BUY" if buys > sells else "SELL"
