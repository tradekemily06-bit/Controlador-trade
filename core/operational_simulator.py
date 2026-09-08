from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .market_data import Candle
from .models import Signal


class SimulationStage(str):
    SIGNAL = "SIGNAL"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    WAITING = "WAITING"
    EXECUTED = "EXECUTED"


class SimulationDecisionValue(str):
    EXECUTAR = "EXECUTAR"
    BLOQUEAR = "BLOQUEAR"
    AGUARDAR = "AGUARDAR"


@dataclass(frozen=True)
class SimulationDecision:
    signal: Signal
    decision: str
    reason: str


@dataclass(frozen=True)
class SimulationRecord:
    index: int
    timestamp: object
    close: float
    signal: Signal
    stage: str
    decision: str
    reason: str


@dataclass(frozen=True)
class SimulationResult:
    records: list[SimulationRecord]
    total_candles: int
    signals: int
    approved: int
    blocked: int
    waiting: int
    executed: int


class OperationalSimulator:
    """Modo laboratório cronológico, sem corretora e sem alterar a decisão."""

    def run(
        self,
        *,
        candles: Iterable[Candle],
        decision_function: Callable[[list[Candle]], SimulationDecision],
    ) -> SimulationResult:
        candles = list(candles)
        if not candles:
            raise ValueError("É necessário fornecer candles.")

        records: list[SimulationRecord] = []
        valid_decisions = {
            SimulationDecisionValue.EXECUTAR,
            SimulationDecisionValue.BLOQUEAR,
            SimulationDecisionValue.AGUARDAR,
        }

        for index in range(len(candles)):
            history = candles[: index + 1]
            result = decision_function(history)
            if not isinstance(result, SimulationDecision):
                raise TypeError("decision_function deve retornar SimulationDecision.")
            if result.decision not in valid_decisions:
                raise ValueError("decision_function retornou decisão inválida.")

            if result.decision == SimulationDecisionValue.AGUARDAR:
                stage = SimulationStage.WAITING
            elif result.decision == SimulationDecisionValue.EXECUTAR:
                stage = SimulationStage.EXECUTED
            else:
                stage = SimulationStage.BLOCKED

            records.append(
                SimulationRecord(
                    index=index,
                    timestamp=candles[index].timestamp,
                    close=candles[index].close,
                    signal=result.signal,
                    stage=stage,
                    decision=result.decision,
                    reason=result.reason,
                )
            )

        return SimulationResult(
            records=records,
            total_candles=len(candles),
            signals=sum(r.signal is not Signal.AGUARDAR for r in records),
            approved=sum(r.decision == SimulationDecisionValue.EXECUTAR for r in records),
            blocked=sum(r.decision == SimulationDecisionValue.BLOQUEAR for r in records),
            waiting=sum(r.decision == SimulationDecisionValue.AGUARDAR for r in records),
            executed=sum(r.stage == SimulationStage.EXECUTED for r in records),
        )
