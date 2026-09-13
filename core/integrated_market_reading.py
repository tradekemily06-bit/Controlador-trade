from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .market_data import Candle
from .methodology_features import extract_candle_features


class ReadingStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class MarketObservation:
    """One auditable market fact/relationship, never an order signal."""

    observation_id: str
    domain: str
    statement: str
    direction: str = "NEUTRAL"
    strength: float = 0.0
    independent_key: str = ""

    def __post_init__(self) -> None:
        if not self.observation_id or not self.domain or not self.statement:
            raise ValueError("observation identity, domain and statement are required")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("observation strength must be between 0 and 1")
        if self.direction not in {"BUY", "SELL", "NEUTRAL"}:
            raise ValueError("invalid observation direction")


@dataclass(frozen=True)
class IntegratedMarketReading:
    status: ReadingStatus
    observations: tuple[MarketObservation, ...]
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    conflicts: tuple[str, ...]
    possible_false_breakout: bool
    unanswered_questions: tuple[str, ...]

    @property
    def independent_confluences(self) -> int:
        """Counts distinct evidence domains, not duplicated signals."""
        return len({o.independent_key or o.domain for o in self.observations if o.strength > 0})


class IntegratedMarketReader:
    """Builds a joint market reading from observable relationships.

    This layer deliberately does not contain COMPRA/VENDA rules or a signal score.
    It describes what is observable, relates independent domains, records agreement
    and conflict, and preserves uncertainty for the decision/validation layers.
    """

    def read(self, candles: list[Candle]) -> IntegratedMarketReading:
        if len(candles) < 2:
            return IntegratedMarketReading(
                ReadingStatus.INSUFFICIENT, (), (), (), (), False,
                ("Há candles suficientes para avaliar o contexto e suas relações?",),
            )

        observations: list[MarketObservation] = []
        latest = candles[-1]
        previous = candles[-2]
        latest_features = extract_candle_features(latest)

        # Candle behavior is factual; it is not treated as a direction by itself.
        observations.append(MarketObservation(
            "candle-body", "candle", "O candle mais recente tem corpo observável em relação ao seu range.",
            "BUY" if latest.close > latest.open else "SELL" if latest.close < latest.open else "NEUTRAL",
            latest_features.body_ratio, "candle_behavior",
        ))
        if latest_features.dominant_wick != "none":
            observations.append(MarketObservation(
                "wick-behavior", "wick", f"O candle mais recente apresenta pavio dominante: {latest_features.dominant_wick}.",
                "NEUTRAL", latest_features.wick_to_body_ratio / (1.0 + latest_features.wick_to_body_ratio), "wick_behavior",
            ))

        # Structural relationship: current close versus previous high/low.
        apparent_breakout = latest.close > previous.high or latest.close < previous.low
        if apparent_breakout:
            direction = "BUY" if latest.close > previous.high else "SELL"
            observations.append(MarketObservation(
                "apparent-breakout", "structure", "O fechamento mais recente saiu do range do candle anterior.",
                direction, 1.0, "structure_breakout",
            ))
            continuation = (
                latest.close > latest.open and latest.close > previous.high
                if direction == "BUY"
                else latest.close < latest.open and latest.close < previous.low
            )
            if continuation:
                observations.append(MarketObservation(
                    "breakout-continuation", "follow_through", "Há continuidade do deslocamento após o rompimento aparente.",
                    direction, 1.0, "post_breakout_behavior",
                ))
            else:
                observations.append(MarketObservation(
                    "breakout-reassessment", "follow_through", "O rompimento aparente não possui continuidade suficiente no candle observado; requer reavaliação.",
                    "NEUTRAL", 1.0, "post_breakout_behavior",
                ))

        directional = {"BUY": 0, "SELL": 0}
        for observation in observations:
            if observation.strength > 0 and observation.direction in directional:
                directional[observation.direction] += 1

        supporting = tuple(o.observation_id for o in observations if o.direction == "BUY" and o.strength > 0)
        contradicting = tuple(o.observation_id for o in observations if o.direction == "SELL" and o.strength > 0)
        conflicts = ()
        status = ReadingStatus.INSUFFICIENT
        if directional["BUY"] and directional["SELL"]:
            status = ReadingStatus.CONFLICTING
            conflicts = ("Há evidências direcionais conflitantes; não transformar contagem em decisão.",)
        elif directional["BUY"] or directional["SELL"]:
            status = ReadingStatus.SUPPORTED

        possible_false_breakout = apparent_breakout and any(
            o.observation_id == "breakout-reassessment" for o in observations
        )
        questions = [
            "Quais relações independentes explicam o movimento observado?",
            "O que sustenta a interpretação e o que a contradiz?",
        ]
        if apparent_breakout:
            questions.append("O rompimento aparente se sustenta ou o contexto posterior sugere uma possível armadilha/rompimento falso?")
        if status is ReadingStatus.CONFLICTING:
            questions.append("Quais evidências estão realmente em conflito e quais são apenas descrições do mesmo fenômeno?")

        return IntegratedMarketReading(
            status=status,
            observations=tuple(observations),
            supporting=supporting,
            contradicting=contradicting,
            conflicts=conflicts,
            possible_false_breakout=possible_false_breakout,
            unanswered_questions=tuple(questions),
        )
