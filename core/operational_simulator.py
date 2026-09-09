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
class SimulationMetrics:
    total_candles: int
    buy_signals: int
    sell_signals: int
    waiting_signals: int
    approved: int
    blocked: int
    waiting: int
    executed: int

    @property
    def signal_rate(self) -> float:
        return (self.buy_signals + self.sell_signals) / self.total_candles if self.total_candles else 0.0

    @property
    def approval_rate(self) -> float:
        return self.approved / self.total_candles if self.total_candles else 0.0

    @property
    def execution_rate(self) -> float:
        return self.executed / self.total_candles if self.total_candles else 0.0


@dataclass(frozen=True)
class SimulationResult:
    records: list[SimulationRecord]
    total_candles: int
    signals: int
    approved: int
    blocked: int
    waiting: int
    executed: int
    metrics: SimulationMetrics


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

        for index in range(1, len(candles)):
            if candles[index].timestamp < candles[index - 1].timestamp:
                raise ValueError("Os candles devem estar em ordem cronológica.")

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

        signals = sum(r.signal is not Signal.AGUARDAR for r in records)
        approved = sum(r.decision == SimulationDecisionValue.EXECUTAR for r in records)
        blocked = sum(r.decision == SimulationDecisionValue.BLOQUEAR for r in records)
        waiting = sum(r.decision == SimulationDecisionValue.AGUARDAR for r in records)
        executed = sum(r.stage == SimulationStage.EXECUTED for r in records)
        buy_signals = sum(r.signal is Signal.COMPRA for r in records)
        sell_signals = sum(r.signal is Signal.VENDA for r in records)
        waiting_signals = sum(r.signal is Signal.AGUARDAR for r in records)

        metrics = SimulationMetrics(
            total_candles=len(candles),
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            waiting_signals=waiting_signals,
            approved=approved,
            blocked=blocked,
            waiting=waiting,
            executed=executed,
        )

        return SimulationResult(
            records=records,
            total_candles=len(candles),
            signals=signals,
            approved=approved,
            blocked=blocked,
            waiting=waiting,
            executed=executed,
            metrics=metrics,
        )
