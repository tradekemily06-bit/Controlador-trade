from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Sequence

from .market_data import Candle
from .models import Signal


@dataclass(frozen=True)
class HistoricalBacktestConfig:
    stop_distance: float
    take_profit_distance: float
    quantity_units: float
    spread_price_units: float
    slippage_price_units_per_side: float
    commission_quote_per_unit_round_turn: float = 0.0
    minimum_directional_score: float = 70.0

    def __post_init__(self) -> None:
        positive = {
            "stop_distance": self.stop_distance,
            "take_profit_distance": self.take_profit_distance,
            "quantity_units": self.quantity_units,
        }
        non_negative = {
            "spread_price_units": self.spread_price_units,
            "slippage_price_units_per_side": self.slippage_price_units_per_side,
            "commission_quote_per_unit_round_turn": self.commission_quote_per_unit_round_turn,
        }
        for name, value in positive.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name} deve ser um número finito maior que zero.")
        for name, value in non_negative.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} deve ser um número finito não negativo.")
        if (
            isinstance(self.minimum_directional_score, bool)
            or not isinstance(self.minimum_directional_score, (int, float))
            or not isfinite(self.minimum_directional_score)
            or not 70 <= self.minimum_directional_score <= 95
        ):
            raise ValueError("minimum_directional_score deve estar entre 70 e 95.")


@dataclass(frozen=True)
class HistoricalSignal:
    signal: Signal
    directional_score: float
    reason: str


@dataclass(frozen=True)
class HistoricalTrade:
    signal_timestamp: str
    entry_timestamp: str
    exit_timestamp: str
    direction: str
    entry_price: float
    exit_price: float
    quantity_units: float
    gross_pnl_quote: float
    spread_cost_quote: float
    slippage_cost_quote: float
    commission_quote: float
    net_pnl_quote: float
    exit_reason: str
    candles_held: int


@dataclass(frozen=True)
class HistoricalBacktestResult:
    trades: tuple[HistoricalTrade, ...]
    candles_processed: int
    candidates: int
    filtered: int
    waiting: int
    wins: int
    losses: int
    breakeven: int
    gross_pnl_quote: float
    total_costs_quote: float
    net_pnl_quote: float
    win_rate: float
    profit_factor: float | None
    orders_sent: bool = False
    execution_allowed: bool = False
    lookahead: bool = False
    simulation_kind: str = "HISTORICAL_OHLC_FIXED_SL_TP"


class HistoricalTradeSimulator:
    """Deterministic OHLC backtest. It has no broker or execution interface."""

    def run(
        self,
        *,
        candles: Iterable[Candle],
        signals: Sequence[HistoricalSignal],
        config: HistoricalBacktestConfig,
    ) -> HistoricalBacktestResult:
        bars = tuple(candles)
        if not bars:
            raise ValueError("É necessário fornecer candles.")
        if len(signals) != len(bars):
            raise ValueError("Deve existir exatamente um sinal por candle.")
        for index, candle in enumerate(bars):
            if not candle.is_valid():
                raise ValueError(f"Candle inválido no índice {index}.")
            if index and candle.timestamp <= bars[index - 1].timestamp:
                raise ValueError("Os candles devem estar em ordem cronológica estritamente crescente.")
        for signal in signals:
            if not isinstance(signal, HistoricalSignal) or not isinstance(signal.signal, Signal):
                raise ValueError("Série de sinais inválida.")
            if (
                isinstance(signal.directional_score, bool)
                or not isinstance(signal.directional_score, (int, float))
                or not isfinite(signal.directional_score)
                or not 0 <= signal.directional_score <= 100
            ):
                raise ValueError("Score direcional inválido.")

        trades: list[HistoricalTrade] = []
        candidates = filtered = waiting = 0
        position = None
        pending = None
        friction_per_side = config.spread_price_units / 2 + config.slippage_price_units_per_side

        for index, bar in enumerate(bars):
            # A signal from the previous completed candle enters at this bar's open.
            if position is None and pending is not None:
                direction, signal_index = pending
                side = 1 if direction == "COMPRA" else -1
                entry_price = bar.open + side * friction_per_side
                position = {
                    "side": side,
                    "direction": direction,
                    "signal_index": signal_index,
                    "entry_index": index,
                    "entry_price": entry_price,
                    "stop": entry_price - side * config.stop_distance,
                    "target": entry_price + side * config.take_profit_distance,
                }
                pending = None

            if position is not None:
                side = position["side"]
                stop_hit = bar.low <= position["stop"] if side == 1 else bar.high >= position["stop"]
                target_hit = bar.high >= position["target"] if side == 1 else bar.low <= position["target"]
                exit_reason = None
                raw_exit = None

                # Conservative OHLC assumption: when both levels are touched,
                # the stop is considered first because intrabar order is unknown.
                if side == 1 and bar.open <= position["stop"]:
                    exit_reason, raw_exit = "STOP_GAP", bar.open
                elif side == -1 and bar.open >= position["stop"]:
                    exit_reason, raw_exit = "STOP_GAP", bar.open
                elif side == 1 and bar.open >= position["target"]:
                    exit_reason, raw_exit = "TAKE_PROFIT_GAP", bar.open
                elif side == -1 and bar.open <= position["target"]:
                    exit_reason, raw_exit = "TAKE_PROFIT_GAP", bar.open
                elif stop_hit:
                    exit_reason, raw_exit = "STOP_LOSS", position["stop"]
                elif target_hit:
                    exit_reason, raw_exit = "TAKE_PROFIT", position["target"]
                elif index == len(bars) - 1:
                    exit_reason, raw_exit = "END_OF_HISTORY", bar.close

                if exit_reason is not None:
                    exit_price = raw_exit - side * friction_per_side
                    gross = (exit_price - position["entry_price"]) * side * config.quantity_units
                    spread_cost = config.spread_price_units * config.quantity_units
                    slippage_cost = 2 * config.slippage_price_units_per_side * config.quantity_units
                    commission = config.commission_quote_per_unit_round_turn * config.quantity_units
                    net = gross - commission
                    # Gross already includes spread/slippage through adjusted fills.
                    # Separate costs are reported for transparency, not subtracted twice.
                    trades.append(HistoricalTrade(
                        signal_timestamp=bars[position["signal_index"]].timestamp.isoformat(),
                        entry_timestamp=bars[position["entry_index"]].timestamp.isoformat(),
                        exit_timestamp=bar.timestamp.isoformat(),
                        direction=position["direction"],
                        entry_price=round(position["entry_price"], 10),
                        exit_price=round(exit_price, 10),
                        quantity_units=config.quantity_units,
                        gross_pnl_quote=round(gross + spread_cost + slippage_cost, 8),
                        spread_cost_quote=round(spread_cost, 8),
                        slippage_cost_quote=round(slippage_cost, 8),
                        commission_quote=round(commission, 8),
                        net_pnl_quote=round(net, 8),
                        exit_reason=exit_reason,
                        candles_held=index - position["entry_index"] + 1,
                    ))
                    position = None

            # Only signals observed at this completed candle can schedule
            # an entry at the next candle open. No same-candle fill is allowed.
            signal = signals[index]
            if position is None and pending is None and index < len(bars) - 1:
                if signal.signal is Signal.AGUARDAR:
                    waiting += 1
                elif signal.directional_score < config.minimum_directional_score:
                    filtered += 1
                else:
                    candidates += 1
                    pending = (signal.signal.value, index)

        gross_total = sum(trade.gross_pnl_quote for trade in trades)
        costs_total = sum(
            trade.spread_cost_quote + trade.slippage_cost_quote + trade.commission_quote
            for trade in trades
        )
        net_total = sum(trade.net_pnl_quote for trade in trades)
        wins = sum(trade.net_pnl_quote > 0 for trade in trades)
        losses = sum(trade.net_pnl_quote < 0 for trade in trades)
        breakeven = sum(trade.net_pnl_quote == 0 for trade in trades)
        gross_profit = sum(trade.net_pnl_quote for trade in trades if trade.net_pnl_quote > 0)
        gross_loss = abs(sum(trade.net_pnl_quote for trade in trades if trade.net_pnl_quote < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        return HistoricalBacktestResult(
            trades=tuple(trades),
            candles_processed=len(bars),
            candidates=candidates,
            filtered=filtered,
            waiting=waiting,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            gross_pnl_quote=round(gross_total, 8),
            total_costs_quote=round(costs_total, 8),
            net_pnl_quote=round(net_total, 8),
            win_rate=(wins / len(trades)) if trades else 0.0,
            profit_factor=round(profit_factor, 6) if profit_factor is not None else None,
        )
