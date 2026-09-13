from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .liquidity_engine import LiquidityEngine
from data.models import Candle
from .market_direction import MarketDirection
from .methodology_features import extract_candle_features
from .trend_engine import TrendEngine
from .volatility_engine import VolatilityEngine


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
        """Count distinct evidence domains, not duplicated descriptions."""
        return len({o.independent_key or o.domain for o in self.observations if o.strength > 0})


class IntegratedMarketReader:
    """Build a joint reading from observable relationships and existing context engines.

    This layer does not contain COMPRA/VENDA rules or an order score. It combines
    factual observations, context, agreement and contradiction. A suspected false
    breakout is only a hypothesis for reassessment, never a fact or an order block.
    """

    def __init__(self, *, trend_engine=None, volatility_engine=None, liquidity_engine=None):
        self.trend_engine = trend_engine or TrendEngine()
        self.volatility_engine = volatility_engine or VolatilityEngine()
        self.liquidity_engine = liquidity_engine or LiquidityEngine()

    def read(self, candles: list[Candle]) -> IntegratedMarketReading:
        if len(candles) < 2:
            return IntegratedMarketReading(
                ReadingStatus.INSUFFICIENT, (), (), (), (), False,
                ("Há histórico suficiente para avaliar o contexto e suas relações?",),
            )

        observations: list[MarketObservation] = []
        latest = candles[-1]
        previous = candles[-2]
        latest_features = extract_candle_features(latest)

        body_direction = (
            "BUY" if latest.close > latest.open else
            "SELL" if latest.close < latest.open else "NEUTRAL"
        )
        observations.append(MarketObservation(
            "candle-body", "candle", "O candle mais recente apresenta corpo mensurável em relação ao próprio range.",
            body_direction, latest_features.body_ratio, "candle_behavior",
        ))

        if latest_features.dominant_wick != "NONE":
            wick_ratio = latest_features.wick_to_body_ratio or 0.0
            observations.append(MarketObservation(
                "wick-behavior", "wick",
                f"O candle mais recente apresenta pavio dominante: {latest_features.dominant_wick}.",
                "NEUTRAL", wick_ratio / (1.0 + wick_ratio), "wick_behavior",
            ))

        if len(candles) >= 3:
            trend = self.trend_engine.evaluate(candles=candles)
            trend_direction = {
                MarketDirection.ALTA: "BUY",
                MarketDirection.BAIXA: "SELL",
                MarketDirection.NEUTRA: "NEUTRAL",
            }[trend.direction]
            observations.append(MarketObservation(
                "trend-context", "structure", trend.reason,
                trend_direction, trend.strength / 100.0, "market_structure",
            ))

        volatility = self.volatility_engine.evaluate(candles=candles)
        observations.append(MarketObservation(
            "volatility-context", "volatility", volatility.reason,
            "NEUTRAL", volatility.score / 100.0, "market_environment",
        ))

        liquidity = self.liquidity_engine.evaluate(candles=candles)
        observations.append(MarketObservation(
            "liquidity-context", "liquidity", liquidity.reason,
            "NEUTRAL", liquidity.score / 100.0, "market_environment",
        ))

        # A breakout is an observable excursion beyond the previous range.
        # Whether it is sustained is assessed separately from the excursion.
        bullish_excursion = latest.high > previous.high
        bearish_excursion = latest.low < previous.low
        apparent_breakout = bullish_excursion or bearish_excursion
        if apparent_breakout:
            if bullish_excursion and bearish_excursion:
                direction = "NEUTRAL"
                breakout_statement = "O candle mais recente excedeu os dois lados do range anterior; o movimento requer reavaliação contextual."
            elif bullish_excursion:
                direction = "BUY"
                breakout_statement = "A máxima mais recente excedeu a máxima anterior; há um rompimento aparente a investigar."
            else:
                direction = "SELL"
                breakout_statement = "A mínima mais recente excedeu para baixo a mínima anterior; há um rompimento aparente a investigar."

            observations.append(MarketObservation(
                "apparent-breakout", "structure", breakout_statement,
                direction, 1.0 if direction != "NEUTRAL" else 0.5, "structure_breakout",
            ))

            continuation = (
                direction == "BUY" and latest.close > previous.high and latest.close > latest.open
            ) or (
                direction == "SELL" and latest.close < previous.low and latest.close < latest.open
            )
            reassessment = not continuation
            observations.append(MarketObservation(
                "breakout-follow-through" if continuation else "breakout-reassessment",
                "follow_through",
                "Há continuidade observável do deslocamento." if continuation else
                "A excursão não apresenta continuidade suficiente no fechamento observado; a interpretação precisa ser reavaliada.",
                direction if continuation else "NEUTRAL", 1.0, "post_breakout_behavior",
            ))
        else:
            reassessment = False

        buy = tuple(o.observation_id for o in observations if o.direction == "BUY" and o.strength > 0)
        sell = tuple(o.observation_id for o in observations if o.direction == "SELL" and o.strength > 0)
        if buy and sell:
            status = ReadingStatus.CONFLICTING
            conflicts = ("Há evidências direcionais conflitantes; não transformar quantidade de sinais em decisão.",)
        elif buy or sell:
            status = ReadingStatus.SUPPORTED
            conflicts = ()
        else:
            status = ReadingStatus.INSUFFICIENT
            conflicts = ()

        # This is a reassessment flag, not a claim that a false breakout occurred.
        # It remains valid even when other observations are directionally conflicting.
        possible_false_breakout = apparent_breakout and reassessment
        questions = [
            "Quais relações independentes explicam o movimento observado?",
            "O que sustenta a interpretação e o que a contradiz?",
            "O contexto de estrutura, volatilidade e liquidez muda a leitura do movimento?",
            "Quais evidências são realmente independentes e quais descrevem o mesmo fenômeno?",
        ]
        if apparent_breakout:
            questions.append("O rompimento aparente se sustenta com o comportamento posterior ou há sinais de possível falso rompimento?")
        if status is ReadingStatus.CONFLICTING:
            questions.append("O que explica a divergência entre as evidências antes de qualquer decisão?")

        return IntegratedMarketReading(
            status=status,
            observations=tuple(observations),
            supporting=buy,
            contradicting=sell,
            conflicts=conflicts,
            possible_false_breakout=possible_false_breakout,
            unanswered_questions=tuple(questions),
        )
