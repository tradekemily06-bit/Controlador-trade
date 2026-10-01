from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import math
from typing import Any

from core.models import Signal
from core.operational_state import OperationalState
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class MT5AdapterError(RuntimeError):
    """Raised when the MT5 runtime cannot be used safely."""


@dataclass(frozen=True)
class ICMarketsMT5DemoConfig:
    """Runtime configuration; credentials are intentionally not stored here."""

    symbol: str | None = None
    deviation: int = 20
    magic: int = 2609001
    risk_day_timezone: str = "UTC"


class ICMarketsMT5DemoAdapter:
    """IC Markets MT5 DEMO boundary.

    Uses the official MetaTrader5 Python package against a running MT5 terminal.
    The adapter stays outside decision/risk logic and rejects REAL requests.
    ``ExecutionRequest.amount`` is interpreted as MT5 volume (lots). MT5 has
    no fixed expiry here; positions remain open until explicitly closed.
    """

    def __init__(self, config: ICMarketsMT5DemoConfig | None = None, mt5_module: Any = None) -> None:
        self.config = config or ICMarketsMT5DemoConfig()
        try:
            self._risk_day_zone = ZoneInfo(self.config.risk_day_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("risk_day_timezone deve ser um timezone IANA válido.")
        self._mt5 = mt5_module

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5AdapterError(
                    "MetaTrader5 não instalado; este adapter precisa de um runtime com MT5."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def is_available(self) -> bool:
        mt5 = None
        try:
            mt5 = self._module()
            if not mt5.initialize():
                return False
            account = mt5.account_info()
            return account is not None and self._is_demo_account(account, mt5)
        except Exception:
            return False
        finally:
            if mt5 is not None:
                try:
                    mt5.shutdown()
                except Exception:
                    pass

    @staticmethod
    def _is_demo_account(account: Any, mt5: Any) -> bool:
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        return demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode

    @staticmethod
    def _valid_volume(amount: float, symbol_info: Any) -> bool:
        """Validate MT5 min/max/step constraints without silently rounding size."""
        if not math.isfinite(amount) or amount <= 0:
            return False

        minimum = getattr(symbol_info, "volume_min", None)
        maximum = getattr(symbol_info, "volume_max", None)
        step = getattr(symbol_info, "volume_step", None)
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in (minimum, maximum, step)
        ):
            return False
        if minimum <= 0 or maximum < minimum or step <= 0:
            return False
        if amount < minimum or amount > maximum:
            return False

        steps = (amount - minimum) / step
        return math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9)

    def read_operational_state(self) -> OperationalState:
        """Read a fail-closed DEMO operational snapshot from MT5."""
        mt5 = self._module()
        if not mt5.initialize():
            raise MT5AdapterError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5AdapterError("conta MT5 não confirmada como DEMO; leitura bloqueada.")
            now = datetime.now(timezone.utc)
            risk_day_now = now.astimezone(self._risk_day_zone)
            risk_day_start = datetime.combine(
                risk_day_now.date(), time.min, tzinfo=self._risk_day_zone
            )
            start = risk_day_start.astimezone(timezone.utc)
            realized_pnl = realized_loss_today = trades_today = consecutive_losses = None
            history_fn = getattr(mt5, "history_deals_get", None)
            if callable(history_fn):
                deals = history_fn(start, now)
                if deals is not None:
                    out = getattr(mt5, "DEAL_ENTRY_OUT", None)
                    out_by = getattr(mt5, "DEAL_ENTRY_OUT_BY", None)
                    closed = [d for d in deals if out is None or getattr(d, "entry", None) in (out, out_by)]
                    profits = [float(getattr(d, "profit", 0.0)) for d in closed]
                    realized_pnl = float(sum(profits))
                    realized_loss_today = float(sum(-profit for profit in profits if profit < 0))
                    trades_today = len(closed)
                    losses = 0
                    for deal in reversed(closed):
                        profit = float(getattr(deal, "profit", 0.0))
                        if profit < 0: losses += 1
                        elif profit > 0: break
                    consecutive_losses = losses
            positions_fn = getattr(mt5, "positions_get", None)
            positions = positions_fn() if callable(positions_fn) else None
            open_positions = net_position = gross_position_volume = exposure = None
            if positions is not None:
                positions = tuple(positions)
                open_positions = len(positions)
                buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)
                net_position = float(sum((1.0 if getattr(p, "type", 0) == buy_type else -1.0) * float(getattr(p, "volume", 0.0)) for p in positions))
                gross_position_volume = float(sum(abs(float(getattr(p, "volume", 0.0))) for p in positions))
                exposure = float(sum(abs(float(getattr(p, "volume", 0.0)) * float(getattr(p, "price_current", 0.0))) for p in positions))
            balance = getattr(account, "balance", None)
            equity = getattr(account, "equity", None)
            unrealized = getattr(account, "profit", None)
            return OperationalState(
                balance=float(balance) if balance is not None else None,
                equity=float(equity) if equity is not None else None,
                realized_pnl=realized_pnl,
                realized_loss_today=realized_loss_today,
                unrealized_pnl=float(unrealized) if unrealized is not None else None,
                trades_today=trades_today,
                consecutive_losses=consecutive_losses,
                open_positions=open_positions,
                net_position=net_position,
                gross_position_volume=gross_position_volume,
                exposure=exposure,
                last_processed_candle=None,
            )
        finally:
            mt5.shutdown()

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        """Read external DEMO order/deal status for P121; never resubmits."""
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido")
        mt5 = self._module()
        if not mt5.initialize():
            raise MT5AdapterError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5AdapterError("conta MT5 não confirmada como DEMO; reconciliação bloqueada.")
            try:
                ticket = int(external_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("external_id deve ser um ticket MT5 numérico") from exc
            deal_fn = getattr(mt5, "history_deals_get", None)
            if callable(deal_fn):
                deals = deal_fn(ticket=ticket)
                if deals:
                    return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "deal externo encontrado no histórico MT5")
            order_fn = getattr(mt5, "history_orders_get", None)
            if callable(order_fn):
                orders = order_fn(ticket=ticket)
                if orders:
                    order = tuple(orders)[-1]
                    state = getattr(order, "state", None)
                    canceled = {getattr(mt5, "ORDER_STATE_CANCELED", object()), getattr(mt5, "ORDER_STATE_REJECTED", object()), getattr(mt5, "ORDER_STATE_EXPIRED", object())}
                    if state in canceled:
                        return ExternalOrderObservation(external_id, ExternalOrderStatus.NOT_EXECUTED, f"ordem externa não executada; state={state}")
                    return ExternalOrderObservation(external_id, ExternalOrderStatus.PENDING, f"ordem externa encontrada; state={state}")
            return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, "ticket externo não encontrado no histórico MT5")
        finally:
            mt5.shutdown()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "IC Markets MT5 adapter aceita somente DEMO.")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não pode gerar ordem.")
        if not math.isfinite(request.amount) or request.amount <= 0:
            return ExecutionResult(False, "volume/amount deve ser maior que zero e finito.")

        mt5 = self._module()
        if not mt5.initialize():
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada como DEMO; ordem bloqueada.")

            symbol = self.config.symbol or request.symbol
            if not isinstance(symbol, str) or not symbol.strip():
                return ExecutionResult(False, "símbolo inválido; ordem bloqueada.")
            symbol = symbol.strip()
            if not mt5.symbol_select(symbol, True):
                return ExecutionResult(False, f"símbolo não disponível no MT5: {symbol}")

            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None or not self._valid_volume(request.amount, symbol_info):
                return ExecutionResult(False, f"volume inválido para o símbolo {symbol}; ordem bloqueada.")

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return ExecutionResult(False, f"cotação indisponível para {symbol}.")

            is_buy = request.signal is Signal.COMPRA
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            price = tick.ask if is_buy else tick.bid
            if not isinstance(price, (int, float)) or not math.isfinite(float(price)) or price <= 0:
                return ExecutionResult(False, f"cotação inválida para {symbol}; ordem bloqueada.")

            payload = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(request.amount),
                "type": order_type,
                "price": price,
                "deviation": self.config.deviation,
                "magic": self.config.magic,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            check = mt5.order_check(payload)
            if check is None or getattr(check, "retcode", 0) != 0:
                return ExecutionResult(False, f"order_check bloqueou a ordem: {check}; mt5_last_error={self._last_error(mt5)}")

            result = mt5.order_send(payload)
            if result is None:
                return ExecutionResult(False, f"order_send sem confirmação: {self._last_error(mt5)}")

            retcode = getattr(result, "retcode", None)
            success_code = getattr(mt5, "TRADE_RETCODE_DONE", None)
            if success_code is None or retcode != success_code:
                return ExecutionResult(False, f"ordem rejeitada pelo MT5: retcode={retcode}")

            external_id = getattr(result, "order", None) or getattr(result, "deal", None)
            if external_id is None:
                return ExecutionResult(
                    False,
                    "MT5 aceitou a ordem, mas não forneceu identificador externo; confirmação bloqueada.",
                )

            return ExecutionResult(True, "ordem DEMO enviada e confirmada pelo MT5.", str(external_id))
        finally:
            mt5.shutdown()

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
