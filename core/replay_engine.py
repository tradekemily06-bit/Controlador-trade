from dataclasses import dataclass
from typing import Callable, Iterable

from .market_data import Candle


@dataclass(frozen=True)
class ReplayRecord:
    timestamp: object
    close: float
    decision: str
    signal: str
    reason: str


@dataclass(frozen=True)
class ReplayResult:
    records: list[ReplayRecord]
    total_candles: int
    executed: int
    blocked: int
    waiting: int


class ReplayEngine:
    """Reproduz decisões sobre candles históricos em ordem cronológica."""

    def run(
        self,
        *,
        candles: Iterable[Candle],
        decision_function: Callable[[Candle], object],
    ) -> ReplayResult:
        candles = list(candles)

        if not candles:
            raise ValueError("É necessário fornecer candles.")

        records = []

        for candle in candles:
            result = decision_function(candle)

            records.append(
                ReplayRecord(
                    timestamp=candle.timestamp,
                    close=candle.close,
                    decision=result.decision,
                    signal=result.signal.value,
                    reason=result.reason,
                )
            )

        executed = sum(
            record.decision == "EXECUTAR"
            for record in records
        )
        blocked = sum(
            record.decision == "BLOQUEAR"
            for record in records
        )
        waiting = sum(
            record.decision == "AGUARDAR"
            for record in records
        )

        return ReplayResult(
            records=records,
            total_candles=len(candles),
            executed=executed,
            blocked=blocked,
            waiting=waiting,
        )
