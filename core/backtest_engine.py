from dataclasses import dataclass
from enum import Enum

from .market_data import Candle
from .models import Signal


class TradeResult(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    AMBOS = "AMBOS"
    PENDENTE = "PENDENTE"


@dataclass(frozen=True)
class BacktestTrade:
    entry_timestamp: object
    entry_price: float
    signal: Signal
    take_profit: float
    stop_loss: float
    result: TradeResult
    exit_timestamp: object | None
    exit_price: float | None
    profit: float


@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade]
    total_trades: int
    wins: int
    losses: int
    ambiguous: int
    pending: int
    total_profit: float
    win_rate: float
    profit_factor: float
    max_consecutive_losses: int
    max_drawdown: float


class BacktestEngine:
    """Simula operações históricas usando TP e SL determinísticos."""

    def run(
        self,
        *,
        candles: list[Candle],
        entry_indexes: list[int],
        signal: Signal,
        take_profit_distance: float,
        stop_loss_distance: float,
    ) -> BacktestResult:
        if not candles:
            raise ValueError("É necessário fornecer candles.")

        if signal not in (Signal.COMPRA, Signal.VENDA):
            raise ValueError("signal deve ser COMPRA ou VENDA.")

        if take_profit_distance <= 0:
            raise ValueError("take_profit_distance deve ser maior que zero.")

        if stop_loss_distance <= 0:
            raise ValueError("stop_loss_distance deve ser maior que zero.")

        trades = []

        for entry_index in entry_indexes:
            if not 0 <= entry_index < len(candles):
                raise ValueError("entry_index fora dos candles fornecidos.")

            entry_candle = candles[entry_index]
            entry_price = entry_candle.close

            if signal == Signal.COMPRA:
                take_profit = entry_price + take_profit_distance
                stop_loss = entry_price - stop_loss_distance
            else:
                take_profit = entry_price - take_profit_distance
                stop_loss = entry_price + stop_loss_distance

            trade = self._simulate_trade(
                candles=candles,
                entry_index=entry_index,
                signal=signal,
                entry_price=entry_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )

            trades.append(trade)

        return self._build_result(trades)

    @staticmethod
    def _simulate_trade(
        *,
        candles,
        entry_index,
        signal,
        entry_price,
        take_profit,
        stop_loss,
    ):
        for candle in candles[entry_index + 1:]:
            if signal == Signal.COMPRA:
                hit_tp = candle.high >= take_profit
                hit_sl = candle.low <= stop_loss

                if hit_tp and hit_sl:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.AMBOS,
                        exit_timestamp=candle.timestamp,
                        exit_price=None,
                        profit=0.0,
                    )

                if hit_tp:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.WIN,
                        exit_timestamp=candle.timestamp,
                        exit_price=take_profit,
                        profit=take_profit - entry_price,
                    )

                if hit_sl:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.LOSS,
                        exit_timestamp=candle.timestamp,
                        exit_price=stop_loss,
                        profit=stop_loss - entry_price,
                    )

            else:
                hit_tp = candle.low <= take_profit
                hit_sl = candle.high >= stop_loss

                if hit_tp and hit_sl:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.AMBOS,
                        exit_timestamp=candle.timestamp,
                        exit_price=None,
                        profit=0.0,
                    )

                if hit_tp:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.WIN,
                        exit_timestamp=candle.timestamp,
                        exit_price=take_profit,
                        profit=entry_price - take_profit,
                    )

                if hit_sl:
                    return BacktestTrade(
                        entry_timestamp=candles[entry_index].timestamp,
                        entry_price=entry_price,
                        signal=signal,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        result=TradeResult.LOSS,
                        exit_timestamp=candle.timestamp,
                        exit_price=stop_loss,
                        profit=entry_price - stop_loss,
                    )

        return BacktestTrade(
            entry_timestamp=candles[entry_index].timestamp,
            entry_price=entry_price,
            signal=signal,
            take_profit=take_profit,
            stop_loss=stop_loss,
            result=TradeResult.PENDENTE,
            exit_timestamp=None,
            exit_price=None,
            profit=0.0,
        )

    @staticmethod
    def _build_result(trades):
        total_trades = len(trades)
        wins = sum(t.result == TradeResult.WIN for t in trades)
        losses = sum(t.result == TradeResult.LOSS for t in trades)
        ambiguous = sum(t.result == TradeResult.AMBOS for t in trades)
        pending = sum(t.result == TradeResult.PENDENTE for t in trades)

        total_profit = sum(t.profit for t in trades)

        decided_trades = wins + losses + ambiguous

        win_rate = (
            (wins / decided_trades) * 100
            if decided_trades
            else 0.0
        )

        gross_profit = sum(
            max(t.profit, 0.0)
            for t in trades
        )
        gross_loss = sum(
            abs(min(t.profit, 0.0))
            for t in trades
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss
            else float("inf") if gross_profit > 0 else 0.0
        )

        current_losses = 0
        max_consecutive_losses = 0

        for trade in trades:
            if trade.result == TradeResult.LOSS:
                current_losses += 1
                max_consecutive_losses = max(
                    max_consecutive_losses,
                    current_losses,
                )
            elif trade.result == TradeResult.WIN:
                current_losses = 0

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for trade in trades:
            equity += trade.profit
            peak = max(peak, equity)
            drawdown = peak - equity
            max_drawdown = max(max_drawdown, drawdown)

        return BacktestResult(
            trades=trades,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            ambiguous=ambiguous,
            pending=pending,
            total_profit=total_profit,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_consecutive_losses=max_consecutive_losses,
            max_drawdown=max_drawdown,
        )
