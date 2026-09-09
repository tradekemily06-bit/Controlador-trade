from dataclasses import dataclass
from typing import Callable, Sequence

from .backtest_engine import BacktestEngine, BacktestResult
from .decision_engine import DecisionResult, FinalDecision
from .market_data import Candle
from .models import Signal


@dataclass(frozen=True)
class HistoricalDecisionRecord:
    index: int
    timestamp: object
    close: float
    decision: str
    signal: Signal
    reason: str


@dataclass(frozen=True)
class HistoricalValidationResult:
    records: list[HistoricalDecisionRecord]
    backtest: BacktestResult
    total_candles: int
    executed: int
    blocked: int
    waiting: int


class HistoricalValidationEngine:
    """Valida decisões em histórico sem expor candles futuros."""

    def __init__(self, backtest_engine: BacktestEngine | None = None) -> None:
        self.backtest_engine = backtest_engine or BacktestEngine()

    def run(
        self,
        *,
        candles: Sequence[Candle],
        decision_function: Callable[[Sequence[Candle]], DecisionResult],
        take_profit_distance: float,
        stop_loss_distance: float,
        min_history: int = 1,
    ) -> HistoricalValidationResult:
        candles = list(candles)
        if not candles:
            raise ValueError("É necessário fornecer candles.")
        if min_history < 1:
            raise ValueError("min_history deve ser maior ou igual a 1.")
        if min_history > len(candles):
            raise ValueError("min_history não pode exceder o número de candles.")

        for index, candle in enumerate(candles):
            if not candle.is_valid():
                raise ValueError(f"Candle inválido no índice {index}.")
            if index and candle.timestamp <= candles[index - 1].timestamp:
                raise ValueError("Candles devem estar em ordem cronológica estrita, sem duplicatas.")

        records: list[HistoricalDecisionRecord] = []
        entry_indexes: list[int] = []
        entry_signals: list[Signal] = []

        for index in range(min_history - 1, len(candles)):
            history = tuple(candles[: index + 1])
            result = decision_function(history)
            if not isinstance(result, DecisionResult):
                raise ValueError("decision_function deve retornar DecisionResult.")

            records.append(
                HistoricalDecisionRecord(
                    index=index,
                    timestamp=candles[index].timestamp,
                    close=candles[index].close,
                    decision=result.decision,
                    signal=result.signal,
                    reason=result.reason,
                )
            )

            if result.decision == FinalDecision.EXECUTAR:
                if result.signal not in (Signal.COMPRA, Signal.VENDA):
                    raise ValueError("EXECUTAR exige sinal COMPRA ou VENDA.")
                entry_indexes.append(index)
                entry_signals.append(result.signal)
            elif result.decision not in (FinalDecision.BLOQUEAR, FinalDecision.AGUARDAR):
                raise ValueError("Decisão histórica inválida.")

        trades = []
        for index, signal in zip(entry_indexes, entry_signals):
            entry_price = candles[index].close
            if signal == Signal.COMPRA:
                take_profit = entry_price + take_profit_distance
                stop_loss = entry_price - stop_loss_distance
            else:
                take_profit = entry_price - take_profit_distance
                stop_loss = entry_price + stop_loss_distance

            trades.append(
                self.backtest_engine._simulate_trade(
                    candles=candles,
                    entry_index=index,
                    signal=signal,
                    entry_price=entry_price,
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                )
            )

        backtest = self.backtest_engine._build_result(trades)
        return HistoricalValidationResult(
            records=records,
            backtest=backtest,
            total_candles=len(candles),
            executed=sum(r.decision == FinalDecision.EXECUTAR for r in records),
            blocked=sum(r.decision == FinalDecision.BLOQUEAR for r in records),
            waiting=sum(r.decision == FinalDecision.AGUARDAR for r in records),
        )
