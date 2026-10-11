from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
import os
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


@dataclass(frozen=True)
class MT5DemoTradeOutcome:
    """Individual result proven by closed DEMO position history only."""

    external_id: str
    position_id: int | None
    outcome: str
    financial_result: float | None
    observed_at: datetime
    source: str
    closed: bool
    message: str
    closed_at: datetime | None = None


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
        except (ZoneInfoNotFoundError, ValueError) as exc:
            # UTC has a fixed offset and is available in the standard library.
            # Keep the default runtime portable when optional tzdata is missing.
            if self.config.risk_day_timezone.strip().upper() in {"UTC", "ETC/UTC", "GMT", "ETC/GMT"}:
                self._risk_day_zone = timezone.utc
            else:
                raise ValueError("risk_day_timezone deve ser um timezone IANA válido.") from exc
        self._mt5 = mt5_module
        self._last_initialization_error = ""

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
            if not self._initialize_mt5(mt5):
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

    def _initialize_mt5(self, mt5: Any) -> bool:
        """Initialize only the configured terminal, with a bounded wait.

        The deployment supervisor sets CONTROLADOR_MT5_TERMINAL_PATH. If that
        path cannot be confirmed, do not silently attach to another terminal.
        """
        configured_path = os.environ.get("CONTROLADOR_MT5_TERMINAL_PATH", "").strip()
        try:
            initialized = bool(
                mt5.initialize(path=configured_path, timeout=15_000)
                if configured_path
                else mt5.initialize(timeout=15_000)
            )
            if not initialized:
                self._last_initialization_error = f"MT5 indisponível: {self._last_error(mt5)}"
                return False

            terminal = mt5.terminal_info()
            if terminal is None or not bool(getattr(terminal, "connected", False)):
                self._last_initialization_error = "terminal MT5 não conectado após initialize"
                mt5.shutdown()
                return False

            if configured_path:
                expected = os.path.normcase(os.path.realpath(configured_path))
                actual = os.path.normcase(
                    os.path.realpath(
                        os.path.join(
                            getattr(terminal, "path", ""),
                            os.path.basename(configured_path),
                        )
                    )
                )
                if actual != expected:
                    self._last_initialization_error = (
                        "terminal MT5 conectado não corresponde ao caminho configurado"
                    )
                    mt5.shutdown()
                    return False

            self._last_initialization_error = ""
            return True
        except Exception as exc:
            self._last_initialization_error = f"falha ao inicializar MT5: {exc}"
            try:
                mt5.shutdown()
            except Exception:
                pass
            return False

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
        if not self._initialize_mt5(mt5):
            raise MT5AdapterError(self._last_initialization_error or f"MT5 indisponível: {self._last_error(mt5)}")
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
        if not self._initialize_mt5(mt5):
            raise MT5AdapterError((self._last_initialization_error or f"MT5 indisponível: {self._last_error(mt5)}"))
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
                deals = tuple(deal_fn(ticket=ticket) or ())
                if any(getattr(deal, "magic", None) == self.config.magic for deal in deals):
                    return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "deal do Controlador encontrado no histórico MT5")
            order_fn = getattr(mt5, "history_orders_get", None)
            if callable(order_fn):
                orders = tuple(order_fn(ticket=ticket) or ())
                if orders:
                    order = orders[-1]
                    if getattr(order, "magic", None) != self.config.magic:
                        return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, "ticket de ordem não pertence ao Controlador; reconciliação bloqueada")
                    state = getattr(order, "state", None)
                    filled = {value for value in (
                        getattr(mt5, "ORDER_STATE_FILLED", None),
                        getattr(mt5, "ORDER_STATE_PARTIAL", None),
                    ) if value is not None}
                    canceled = {value for value in (
                        getattr(mt5, "ORDER_STATE_CANCELED", None),
                        getattr(mt5, "ORDER_STATE_REJECTED", None),
                        getattr(mt5, "ORDER_STATE_EXPIRED", None),
                    ) if value is not None}
                    if state in filled:
                        return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, f"ordem externa executada; state={state}")
                    if state in canceled:
                        # A canceled order may still have partial fills. Verify its position history
                        # before declaring it not executed, and never accept deals from another magic.
                        position_id = getattr(order, "position_id", None)
                        if position_id is not None and int(position_id) > 0 and callable(deal_fn):
                            try:
                                position_deals = deal_fn(position=int(position_id))
                            except (TypeError, AttributeError):
                                return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, "histórico da posição indisponível para validar execução parcial")
                            if position_deals is None:
                                return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, "histórico da posição indisponível para validar execução parcial")
                            if any(
                                int(getattr(deal, "position_id", -1)) == int(position_id)
                                and int(getattr(deal, "order", -1)) == ticket
                                and getattr(deal, "magic", None) == self.config.magic
                                for deal in position_deals
                            ):
                                return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "ordem parcialmente executada confirmada no histórico MT5")
                        return ExternalOrderObservation(external_id, ExternalOrderStatus.NOT_EXECUTED, f"ordem externa não executada; state={state}")
                    return ExternalOrderObservation(external_id, ExternalOrderStatus.PENDING, f"ordem externa encontrada; state={state}")
            return ExternalOrderObservation(external_id, ExternalOrderStatus.UNKNOWN, "ticket externo não encontrado no histórico MT5")
        finally:
            mt5.shutdown()

    def query_trade_outcome(self, external_id: str) -> MT5DemoTradeOutcome:
        """Attribute net P&L only after the exact owned DEMO position is closed.

        Order acceptance is not a trade result. Missing identity, unavailable
        history, an open position, or missing exit deals therefore stays UNKNOWN.
        """
        observed_at = datetime.now(timezone.utc)
        unknown = lambda position_id, message: MT5DemoTradeOutcome(
            external_id=str(external_id), position_id=position_id, outcome="UNKNOWN",
            financial_result=None, observed_at=observed_at,
            source="MT5_DEMO_HISTORY", closed=False, message=message,
        )
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido")
        mt5 = self._module()
        if not self._initialize_mt5(mt5):
            raise MT5AdapterError((self._last_initialization_error or f"MT5 indisponível: {self._last_error(mt5)}"))
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5AdapterError("conta MT5 não confirmada como DEMO; resultado bloqueado.")
            try:
                ticket = int(external_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("external_id deve ser um ticket MT5 numérico") from exc

            position_id = None
            deal_fn = getattr(mt5, "history_deals_get", None)
            if callable(deal_fn):
                for deal in tuple(deal_fn(ticket=ticket) or ()):
                    candidate = getattr(deal, "position_id", None)
                    if (candidate is not None and int(candidate) > 0
                            and getattr(deal, "magic", None) == self.config.magic):
                        position_id = int(candidate)
                        break
            if position_id is None:
                order_fn = getattr(mt5, "history_orders_get", None)
                if callable(order_fn):
                    for order in tuple(order_fn(ticket=ticket) or ()):
                        candidate = getattr(order, "position_id", None)
                        if (candidate is not None and int(candidate) > 0
                                and getattr(order, "magic", None) == self.config.magic):
                            position_id = int(candidate)
                            break
            if position_id is None:
                return unknown(None, "ticket não associado de forma verificável a uma posição do Controlador.")

            positions_fn = getattr(mt5, "positions_get", None)
            positions = positions_fn() if callable(positions_fn) else None
            if positions is None:
                return unknown(position_id, "histórico de posições indisponível; fechamento não confirmado.")
            if any(int(getattr(position, "ticket", -1)) == position_id for position in positions):
                return unknown(position_id, "posição ainda aberta; resultado final não atribuído.")

            if not callable(deal_fn):
                return unknown(position_id, "histórico de negócios indisponível.")
            try:
                position_deals = tuple(deal_fn(position=position_id) or ())
            except (TypeError, AttributeError):
                return unknown(position_id, "consulta de histórico por posição não suportada.")
            relevant = tuple(
                deal for deal in position_deals
                if int(getattr(deal, "position_id", -1)) == position_id
                and getattr(deal, "magic", None) == self.config.magic
            )
            exit_values = {
                value for value in (
                    getattr(mt5, "DEAL_ENTRY_OUT", None),
                    getattr(mt5, "DEAL_ENTRY_OUT_BY", None),
                ) if value is not None
            }
            exit_deals = tuple(deal for deal in relevant if getattr(deal, "entry", None) in exit_values)
            if not relevant or not exit_values or not exit_deals:
                return unknown(position_id, "não há negócio de saída confirmado para esta posição.")
            # Period statistics use the final exit timestamp from MT5 history,
            # not the later time at which an operator/runtime happened to reconcile.
            close_times = []
            for deal in exit_deals:
                raw_msc = getattr(deal, "time_msc", None)
                raw_seconds = getattr(deal, "time", None)
                try:
                    timestamp = float(raw_msc) / 1000.0 if raw_msc not in (None, 0) else float(raw_seconds)
                    if math.isfinite(timestamp) and timestamp > 0:
                        close_times.append(datetime.fromtimestamp(timestamp, tz=timezone.utc))
                except (TypeError, ValueError, OverflowError, OSError):
                    continue
            closed_at = max(close_times) if close_times else None
            entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
            entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", object())
            # Netting/reversal positions can combine several orders under one position_id.
            # Do not assign their aggregate P&L to a single cycle.
            opening_orders = {
                int(getattr(deal, "order", -1))
                for deal in relevant
                if getattr(deal, "entry", None) == entry_in
                and getattr(deal, "order", None) is not None
            }
            if entry_inout in {getattr(deal, "entry", None) for deal in relevant} or opening_orders != {ticket}:
                return unknown(position_id, "posição contém identidade de entrada ambígua; resultado não atribuído.")

            net_result = sum(
                float(getattr(deal, "profit", 0.0) or 0.0)
                + float(getattr(deal, "commission", 0.0) or 0.0)
                + float(getattr(deal, "swap", 0.0) or 0.0)
                + float(getattr(deal, "fee", 0.0) or 0.0)
                for deal in relevant
            )
            if not math.isfinite(net_result):
                return unknown(position_id, "resultado líquido não finito; atribuição bloqueada.")
            outcome = "WIN" if net_result > 0 else "LOSS" if net_result < 0 else "DRAW"
            return MT5DemoTradeOutcome(
                external_id=external_id, position_id=position_id, outcome=outcome,
                financial_result=float(net_result), observed_at=observed_at,
                source="MT5_DEMO_HISTORY", closed=True,
                message="resultado líquido confirmado no histórico da posição DEMO.",
                closed_at=closed_at,
            )
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
        if not self._initialize_mt5(mt5):
            return ExecutionResult(False, (self._last_initialization_error or f"MT5 indisponível: {self._last_error(mt5)}"))

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

    def close_position(self, external_id: str) -> ExecutionResult:
        """Close only the confirmed DEMO position identified by this adapter's order ticket."""
        if not isinstance(external_id, str) or not external_id.strip():
            return ExecutionResult(False, "external_id inválido; fechamento bloqueado.")
        mt5 = self._module()
        if not self._initialize_mt5(mt5):
            return ExecutionResult(False, (self._last_initialization_error or f"MT5 indisponível: {self._last_error(mt5)}"))
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada como DEMO; fechamento bloqueado.")
            try:
                target_ticket = int(external_id)
            except (TypeError, ValueError):
                return ExecutionResult(False, "external_id deve ser um ticket MT5 numérico.")

            # Opening results expose an order/deal ticket, while MT5 can assign
            # a distinct position ticket. Resolve the external identity to the
            # exact owned position before sending a close.
            position_ticket = None
            deal_fn = getattr(mt5, "history_deals_get", None)
            if callable(deal_fn):
                deals = tuple(deal_fn(ticket=target_ticket) or ())
                for deal in reversed(deals):
                    candidate = getattr(deal, "position_id", None)
                    if candidate is not None and int(candidate) > 0:
                        position_ticket = int(candidate)
                        break
            if position_ticket is None:
                order_fn = getattr(mt5, "history_orders_get", None)
                if callable(order_fn):
                    orders = tuple(order_fn(ticket=target_ticket) or ())
                    for order in reversed(orders):
                        candidate = getattr(order, "position_id", None)
                        if candidate is not None and int(candidate) > 0:
                            position_ticket = int(candidate)
                            break
            if position_ticket is None:
                return ExecutionResult(False, "external_id não pôde ser associado a uma posição MT5; fechamento bloqueado.")

            positions = tuple(mt5.positions_get() or ())
            matches = tuple(
                p for p in positions
                if int(getattr(p, "ticket", -1)) == position_ticket
                and int(getattr(p, "magic", -1)) == self.config.magic
            )
            if len(matches) != 1:
                return ExecutionResult(False, "posição DEMO do Controlador não encontrada de forma única; fechamento bloqueado.")
            position = matches[0]
            symbol = str(getattr(position, "symbol", "")).strip()
            volume = float(getattr(position, "volume", 0.0))
            position_type = getattr(position, "type", None)
            buy_type = getattr(mt5, "POSITION_TYPE_BUY", None)
            sell_type = getattr(mt5, "POSITION_TYPE_SELL", None)
            if buy_type is None or sell_type is None or position_type not in (buy_type, sell_type):
                return ExecutionResult(False, "tipo de posição MT5 inválido; fechamento bloqueado.")
            close_type = mt5.ORDER_TYPE_SELL if position_type == buy_type else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return ExecutionResult(False, f"cotação indisponível para fechamento de {symbol}.")
            price = float(tick.bid if position_type == buy_type else tick.ask)
            if not math.isfinite(price) or price <= 0 or not math.isfinite(volume) or volume <= 0:
                return ExecutionResult(False, "preço/volume inválido para fechamento; ordem bloqueada.")
            payload = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "position": int(position.ticket),
                "price": price,
                "deviation": self.config.deviation,
                "magic": self.config.magic,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            check = mt5.order_check(payload)
            if check is None or getattr(check, "retcode", 0) != 0:
                return ExecutionResult(False, f"order_check do fechamento bloqueou a ordem: {check}; mt5_last_error={self._last_error(mt5)}")
            result = mt5.order_send(payload)
            if result is None or getattr(result, "retcode", None) != getattr(mt5, "TRADE_RETCODE_DONE", None):
                return ExecutionResult(False, f"fechamento rejeitado pelo MT5: {result}; mt5_last_error={self._last_error(mt5)}")
            close_external_id = getattr(result, "order", None) or getattr(result, "deal", None)
            if close_external_id is None:
                return ExecutionResult(False, "MT5 confirmou fechamento sem identificador externo.")
            remaining = tuple(
                p for p in (mt5.positions_get() or ())
                if int(getattr(p, "magic", -1)) == self.config.magic
                and str(getattr(p, "symbol", "")).strip() == symbol
            )
            if any(int(getattr(p, "ticket", -1)) == int(position.ticket) for p in remaining):
                return ExecutionResult(False, "MT5 confirmou o fechamento, mas a posição Controlador ainda permanece aberta.")
            return ExecutionResult(True, "posição DEMO fechada e confirmada pelo MT5.", str(close_external_id))
        finally:
            mt5.shutdown()

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"


class ICMarketsMT5RealAdapter(ICMarketsMT5DemoAdapter):
    """IC Markets MT5 REAL boundary used only behind the REAL gateway.

    The inherited MT5 mechanics are deliberately reused so DEMO and REAL do
    not diverge in order construction, position identity, or reconciliation.
    This adapter accepts only REAL requests and only a MT5 account explicitly
    classified as REAL. It never handles broker credentials.
    """

    @staticmethod
    def _is_demo_account(account: Any, mt5: Any) -> bool:
        real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", None)
        return real_mode is not None and getattr(account, "trade_mode", None) == real_mode

    def query_trade_outcome(self, external_id: str) -> MT5DemoTradeOutcome:
        """Never label REAL account history as DEMO statistics."""
        raise MT5AdapterError("atribuição de resultado MT5_DEMO_HISTORY não está disponível no adapter REAL.")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.mode is not ExecutionMode.REAL:
            return ExecutionResult(False, "IC Markets MT5 REAL adapter aceita somente REAL.")
        # Reuse the proven MT5 execution mechanics while keeping the request
        # boundary explicit. The inherited implementation performs the same
        # account, symbol, volume, quote, order_check and order_send checks;
        # the subclass account predicate above makes those checks REAL-only.
        from dataclasses import replace
        demo_shaped_request = replace(request, mode=ExecutionMode.DEMO)
        result = super().execute(demo_shaped_request)
        if result.accepted:
            return ExecutionResult(True, "ordem REAL enviada e confirmada pelo MT5.", result.external_id)
        return result
