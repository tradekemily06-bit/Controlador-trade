from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import math
import hashlib
import os
from typing import Any

from core.models import Signal
from core.operational_state import OperationalState
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from execution.ports import (
    ExecutionMode, ExecutionRequest, ExecutionResult,
    PositionCloseObservation, PositionCloseObservationStatus,
)


class MT5AdapterError(RuntimeError):
    """Raised when the MT5 runtime cannot be used safely."""


class MT5DealNotFoundError(MT5AdapterError):
    """Raised when MT5 is available but the requested closed deal is absent."""


@dataclass(frozen=True)
class ICMarketsMT5DemoConfig:
    """Runtime configuration; credentials are intentionally not stored here."""

    symbol: str | None = None
    deviation: int = 20
    magic: int = 2609001
    risk_day_timezone: str = "UTC"
    terminal_path: str | None = None


class ICMarketsMT5DemoAdapter:
    requires_account_fingerprint = False
    """IC Markets MT5 DEMO boundary.

    Uses the official MetaTrader5 Python package against a running MT5 terminal.
    The adapter stays outside decision/risk logic and rejects REAL requests.
    ``ExecutionRequest.amount`` is interpreted as MT5 volume (lots). MT5 has
    no fixed expiry here; positions remain open until explicitly closed.
    """

    def __init__(self, config: ICMarketsMT5DemoConfig | None = None, mt5_module: Any = None) -> None:
        self.config = config or ICMarketsMT5DemoConfig()
        try:
            # UTC has no daylight-saving rules and is available directly from
            # the standard library. Keep the default runtime independent of
            # the external tzdata package, which can be incomplete on Windows.
            if self.config.risk_day_timezone == "UTC":
                self._risk_day_zone = timezone.utc
            else:
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

    def _initialize(self, mt5: Any) -> bool:
        """Initialize only the configured terminal; reject a different MT5 instance."""
        terminal_path = self.config.terminal_path or os.environ.get("CONTROLADOR_MT5_TERMINAL_PATH") or None
        try:
            if not terminal_path:
                return bool(mt5.initialize())
            if not mt5.initialize(path=terminal_path):
                return False
            terminal = mt5.terminal_info()
            expected = os.path.normcase(os.path.realpath(terminal_path))
            actual = (
                os.path.normcase(
                    os.path.realpath(
                        os.path.join(getattr(terminal, "path", ""), os.path.basename(terminal_path))
                    )
                )
                if terminal is not None
                else ""
            )
            if actual != expected:
                mt5.shutdown()
                return False
            return True
        except Exception:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return False

    def is_available(self) -> bool:
        mt5 = None
        try:
            mt5 = self._module()
            if not self._initialize(mt5):
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
    def _account_fingerprint(account: Any) -> str | None:
        """Return a stable pseudonymous key; never return the raw login or server."""
        login = getattr(account, "login", None)
        login_text = str(login).strip() if login is not None else ""
        server = str(getattr(account, "server", "") or "").strip()
        # MT5 account logins are positive numeric identifiers. Refuse partial or
        # malformed identity rather than creating a weak, collision-prone key.
        if (
            not login_text.isascii()
            or not login_text.isdigit()
            or len(login_text) > 20
            or int(login_text or "0") <= 0
            or not server
            or len(server) > 255
            or any(ord(char) < 32 or ord(char) == 127 for char in server)
        ):
            return None
        raw = f"{server.casefold()}|{login_text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

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
        """Read a fail-closed DEMO operational snapshot from MT5.

        Daily P&L includes deal profit, commission, swap and fee. Operation
        counts are deduplicated by position identifier; a partial close is
        not counted as a second trade. If MT5 omits identifiers or the
        position history is insufficient to establish a completed trade,
        the consecutive-loss field remains unknown and risk gates fail closed.
        """
        mt5 = self._module()
        if not self._initialize(mt5):
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

            open_positions = net_position = gross_position_volume = exposure = None
            open_position_ids: set[str] = set()
            positions_known = False
            positions_fn = getattr(mt5, "positions_get", None)
            positions = positions_fn() if callable(positions_fn) else None
            if positions is not None:
                positions = tuple(positions)
                positions_known = True
                open_positions = len(positions)
                buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)
                net_position = float(sum(
                    (1.0 if getattr(position, "type", 0) == buy_type else -1.0)
                    * float(getattr(position, "volume", 0.0))
                    for position in positions
                ))
                gross_position_volume = float(sum(
                    abs(float(getattr(position, "volume", 0.0)))
                    for position in positions
                ))
                exposure = float(sum(
                    abs(
                        float(getattr(position, "volume", 0.0))
                        * float(getattr(position, "price_current", 0.0))
                    )
                    for position in positions
                ))
                for position in positions:
                    identifier = getattr(position, "identifier", None)
                    if identifier is None:
                        identifier = getattr(position, "ticket", None)
                    if identifier is None or not str(identifier).strip():
                        positions_known = False
                    else:
                        open_position_ids.add(str(identifier))

            realized_pnl = realized_loss_today = trades_today = consecutive_losses = None
            history_fn = getattr(mt5, "history_deals_get", None)
            if callable(history_fn):
                deals = history_fn(start, now)
                if deals is not None:
                    deals = tuple(deals)
                    entry_in = getattr(mt5, "DEAL_ENTRY_IN", None)
                    entry_out = getattr(mt5, "DEAL_ENTRY_OUT", None)
                    entry_out_by = getattr(mt5, "DEAL_ENTRY_OUT_BY", None)
                    entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", None)
                    closing_entries = {value for value in (entry_out, entry_out_by) if value is not None}

                    def deal_cashflow(deal):
                        total = 0.0
                        for field in ("profit", "commission", "swap", "fee"):
                            value = getattr(deal, field, 0.0)
                            if (
                                isinstance(value, bool)
                                or not isinstance(value, (int, float))
                                or not math.isfinite(float(value))
                            ):
                                return None
                            total += float(value)
                        return total

                    cashflows = [deal_cashflow(deal) for deal in deals]
                    if all(value is not None for value in cashflows):
                        realized_pnl = float(sum(cashflows))

                    identifiers = []
                    entries_valid = True
                    for deal in deals:
                        identifier = getattr(deal, "position_id", None)
                        if identifier is None:
                            identifier = getattr(deal, "position", None)
                        if identifier is None or not str(identifier).strip():
                            entries_valid = False
                            identifiers.append(None)
                        else:
                            identifiers.append(str(identifier))

                    has_netting_reversal = (
                        entry_inout is not None
                        and any(getattr(deal, "entry", None) == entry_inout for deal in deals)
                    )
                    if entries_valid and not has_netting_reversal:
                        trades_today = len(set(identifiers))
                    grouped = {}
                    for index, (deal, identifier, cashflow) in enumerate(zip(deals, identifiers, cashflows)):
                        if identifier is None:
                            continue
                        grouped.setdefault(identifier, []).append((index, deal, cashflow))

                    # P40 consumes the sum of losing position results, not the
                    # net account P&L. Missing identity or netting reversal makes
                    # this counter unknown so the execution budget fails closed.
                    if all(value is not None for value in cashflows) and entries_valid and not has_netting_reversal:
                        realized_loss_today = float(sum(
                            -position_total
                            for rows in grouped.values()
                            if (position_total := sum(value for _, _, value in rows)) < 0
                        ))

                    closed_ids = {
                        identifier
                        for identifier, rows in grouped.items()
                        if any(getattr(deal, "entry", None) in closing_entries for _, deal, _ in rows)
                    }
                    entry_data_valid = all(getattr(deal, "entry", None) is not None for deal in deals)
                    if has_netting_reversal:
                        consecutive_losses = None
                    elif not closed_ids:
                        consecutive_losses = 0 if entries_valid and entry_data_valid else None
                    elif (
                        not entries_valid
                        or not entry_data_valid
                        or not positions_known
                        or entry_in is None
                    ):
                        consecutive_losses = None
                    else:
                        completed = []
                        incomplete = False
                        for identifier in closed_ids:
                            if identifier in open_position_ids:
                                continue
                            rows = grouped[identifier]
                            if not any(getattr(deal, "entry", None) == entry_in for _, deal, _ in rows):
                                # The opening leg may predate today's history window;
                                # its fees are unknown, so the final trade result is unknown.
                                incomplete = True
                                continue
                            if any(value is None for _, _, value in rows):
                                incomplete = True
                                continue
                            close_rows = [
                                (index, deal)
                                for index, deal, _ in rows
                                if getattr(deal, "entry", None) in closing_entries
                            ]
                            if not close_rows:
                                continue
                            def close_order(pair):
                                index, deal = pair
                                milliseconds = getattr(deal, "time_msc", None)
                                if isinstance(milliseconds, (int, float)) and milliseconds > 0:
                                    return float(milliseconds)
                                seconds = getattr(deal, "time", None)
                                if isinstance(seconds, (int, float)) and seconds > 0:
                                    return float(seconds) * 1000.0
                                return float(index)

                            last_index, last_close = max(close_rows, key=close_order)
                            net_result = sum(value for _, _, value in rows)
                            completed.append((close_order((last_index, last_close)), net_result))
                        if incomplete:
                            consecutive_losses = None
                        else:
                            streak = 0
                            for _, net_result in sorted(completed, key=lambda item: item[0], reverse=True):
                                if net_result < 0:
                                    streak += 1
                                elif net_result > 0:
                                    break
                                else:
                                    break
                            consecutive_losses = streak

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

    def read_closed_deal_candidates(self, lookback_days: int = 30, *, include_private: bool = False) -> dict[str, Any]:
        """Return complete, fully closed DEMO position results for human fiscal review."""
        if not isinstance(lookback_days, int) or isinstance(lookback_days, bool) or not 1 <= lookback_days <= 365:
            raise ValueError("lookback_days deve estar entre 1 e 365")
        mt5 = self._module()
        if not self._initialize(mt5):
            raise MT5AdapterError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5AdapterError("conta MT5 não confirmada como DEMO; consulta fiscal bloqueada.")
            history_fn = getattr(mt5, "history_deals_get", None)
            if not callable(history_fn):
                raise MT5AdapterError("histórico de negócios MT5 indisponível.")
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=lookback_days)
            recent_deals = history_fn(start, end)
            if recent_deals is None:
                raise MT5AdapterError("MT5 não retornou histórico de negócios.")
            entry_in = getattr(mt5, "DEAL_ENTRY_IN", None)
            entry_out = getattr(mt5, "DEAL_ENTRY_OUT", None)
            entry_out_by = getattr(mt5, "DEAL_ENTRY_OUT_BY", None)
            entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", None)
            if entry_in is None or entry_out is None:
                raise MT5AdapterError("MT5 não informou os tipos de entrada/saída; consulta fiscal bloqueada.")
            closing_entries = {entry_out}
            if entry_out_by is not None:
                closing_entries.add(entry_out_by)
            supported_entries = {entry_in, *closing_entries}
            open_positions_fn = getattr(mt5, "positions_get", None)
            if not callable(open_positions_fn):
                raise MT5AdapterError("MT5 não permite verificar posições ainda abertas.")
            open_positions = open_positions_fn()
            if open_positions is None:
                raise MT5AdapterError("MT5 não confirmou o estado das posições abertas.")
            open_position_ids = {
                str(getattr(position, "identifier", None) or getattr(position, "ticket", ""))
                for position in open_positions
            }
            position_ids = {
                str(getattr(deal, "position_id", ""))
                for deal in recent_deals
                if getattr(deal, "entry", None) in closing_entries
                and str(getattr(deal, "position_id", "")).isdigit()
                and int(getattr(deal, "position_id", 0) or 0) > 0
            }
            candidates = []
            withheld = 0
            for position_id in sorted(position_ids):
                if position_id in open_position_ids:
                    withheld += 1
                    continue
                position_deals = history_fn(position=int(position_id))
                if position_deals is None or not position_deals:
                    withheld += 1
                    continue
                position_deals = tuple(position_deals)
                if any(getattr(deal, "entry", None) == entry_inout for deal in position_deals):
                    withheld += 1
                    continue
                if any(getattr(deal, "entry", None) not in supported_entries for deal in position_deals):
                    withheld += 1
                    continue
                opening = [deal for deal in position_deals if getattr(deal, "entry", None) == entry_in]
                closing = [deal for deal in position_deals if getattr(deal, "entry", None) in closing_entries]
                if not opening or not closing:
                    withheld += 1
                    continue
                try:
                    opened_volume = sum(float(getattr(deal, "volume", 0.0) or 0.0) for deal in opening)
                    closed_volume = sum(float(getattr(deal, "volume", 0.0) or 0.0) for deal in closing)
                    components = {
                        key: sum(float(getattr(deal, key, 0.0) or 0.0) for deal in position_deals)
                        for key in ("profit", "commission", "swap", "fee")
                    }
                except (TypeError, ValueError, OverflowError):
                    withheld += 1
                    continue
                if (
                    not math.isfinite(opened_volume)
                    or not math.isfinite(closed_volume)
                    or opened_volume <= 0
                    or closed_volume <= 0
                    or not math.isclose(opened_volume, closed_volume, rel_tol=0.0, abs_tol=max(1e-8, opened_volume * 1e-6))
                    or not all(math.isfinite(value) for value in components.values())
                ):
                    withheld += 1
                    continue
                try:
                    def deal_order_key(deal: Any) -> tuple[int, int, int]:
                        return (
                            int(getattr(deal, "time_msc", 0) or 0),
                            int(getattr(deal, "time", 0) or 0),
                            int(getattr(deal, "ticket", 0) or 0),
                        )

                    opening = sorted(opening, key=deal_order_key)
                    closing = sorted(closing, key=deal_order_key)
                    first_opening_deal = opening[0]
                    final_deal = closing[-1]
                    opening_timestamp = int(getattr(first_opening_deal, "time", 0) or 0)
                    timestamp = int(getattr(final_deal, "time", 0) or 0)
                    ticket = str(getattr(final_deal, "ticket", "") or "")
                    if (
                        not ticket.isdigit()
                        or len(ticket) > 20
                        or opening_timestamp <= 0
                        or timestamp <= 0
                    ):
                        withheld += 1
                        continue
                    opened_at_utc = datetime.fromtimestamp(opening_timestamp, timezone.utc).isoformat()
                    occurred_at_utc = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                except (TypeError, ValueError, OverflowError, OSError):
                    withheld += 1
                    continue
                candidates.append({
                    "ticket": ticket,
                    "position_id": position_id,
                    "symbol": str(getattr(final_deal, "symbol", "") or ""),
                    "volume": opened_volume,
                    **components,
                    "net_result_account_currency": round(sum(components.values()), 8),
                    "account_currency": str(getattr(account, "currency", "") or "UNKNOWN"),
                    "opened_at_utc": opened_at_utc,
                    "occurred_at_utc": occurred_at_utc,
                    "deal_count": len(position_deals),
                    "closing_deal_count": len(closing),
                    "result_scope": "FULL_CLOSED_POSITION",
                })
            return {
                "source": "IC Markets MT5 DEMO",
                "account_currency": str(getattr(account, "currency", "") or "UNKNOWN"),
                **({"account_fingerprint": self._account_fingerprint(account)} if include_private else {}),
                "lookback_days": lookback_days,
                "count": len(candidates),
                "withheld_incomplete_positions": withheld,
                "candidates": candidates,
                "auto_registered": False,
                "notice": "Resultado agregado de todos os negócios da posição totalmente encerrada (entrada, saídas parciais, lucro, comissão, swap e taxas). Posições abertas, histórico incompleto, volume não conciliado ou reversões foram retidos para conferência; nenhum lançamento foi criado.",
            }
        finally:
            mt5.shutdown()

    def read_closed_deal_candidate(self, ticket: str) -> dict[str, Any]:
        """Re-read one exact final closing ticket and its complete DEMO position history."""
        raw_ticket = str(ticket or "").strip()
        if not raw_ticket.isdigit() or len(raw_ticket) > 20:
            raise ValueError("ticket MT5 inválido")
        preview = self.read_closed_deal_candidates(lookback_days=365, include_private=True)
        matches = [
            item for item in preview.get("candidates", [])
            if str(item.get("ticket", "")) == raw_ticket
        ]
        if len(matches) != 1:
            raise MT5DealNotFoundError("ticket não encontrado como encerramento integral e conciliado de posição no histórico DEMO.")
        return {
            **matches[0],
            "source": preview.get("source"),
            "account_currency": preview.get("account_currency"),
            "account_fingerprint": preview.get("account_fingerprint"),
            "auto_registered": False,
            "notice": preview.get("notice"),
        }

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        """Read external DEMO order/deal status for P121; never resubmits."""
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido")
        mt5 = self._module()
        if not self._initialize(mt5):
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
        if not self._initialize(mt5):
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada; ordem bloqueada.")
            account_fingerprint = self._account_fingerprint(account)
            if self.requires_account_fingerprint and account_fingerprint is None:
                return ExecutionResult(
                    False,
                    "identidade pseudônima da conta MT5 indisponível; ordem REAL bloqueada.",
                )

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

            return ExecutionResult(
                True,
                "ordem enviada e confirmada pelo MT5.",
                str(external_id),
                account_fingerprint,
            )
        finally:
            mt5.shutdown()

    def close_position(
        self,
        external_id: str,
        *,
        expected_account_fingerprint: str | None = None,
    ) -> ExecutionResult:
        """Close only the position identified by this adapter's order ticket and account fingerprint."""
        if not isinstance(external_id, str) or not external_id.strip():
            return ExecutionResult(False, "external_id inválido; fechamento bloqueado.")
        mt5 = self._module()
        if not self._initialize(mt5):
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada; fechamento bloqueado.")
            current_fingerprint = self._account_fingerprint(account)
            if self.requires_account_fingerprint and (
                expected_account_fingerprint is None
                or current_fingerprint is None
                or current_fingerprint != expected_account_fingerprint
            ):
                return ExecutionResult(
                    False,
                    "a conta MT5 conectada não corresponde à conta registrada na abertura; fechamento bloqueado.",
                )
            if expected_account_fingerprint is not None and current_fingerprint != expected_account_fingerprint:
                return ExecutionResult(False, "impressão digital da conta MT5 divergente; fechamento bloqueado.")
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
                return ExecutionResult(False, "posição MT5 do Controlador não encontrada de forma única; fechamento bloqueado.")
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
            return ExecutionResult(True, "posição MT5 do Controlador fechada e confirmada pelo MT5.", str(close_external_id))
        finally:
            mt5.shutdown()

    def reconcile_position_close(
        self,
        external_id: str,
        *,
        expected_account_fingerprint: str | None = None,
    ) -> PositionCloseObservation:
        """Read MT5 account, open-position, and deal history; never sends an order."""
        unknown = PositionCloseObservationStatus.UNKNOWN
        if not isinstance(external_id, str) or not external_id.strip():
            return PositionCloseObservation(unknown, "external_id inválido para reconciliação.")
        try:
            target_ticket = int(external_id)
        except (TypeError, ValueError):
            return PositionCloseObservation(unknown, "external_id não é um ticket MT5 numérico.")

        mt5 = self._module()
        if not self._initialize(mt5):
            return PositionCloseObservation(unknown, f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return PositionCloseObservation(unknown, "tipo de conta MT5 não confirmado; reconciliação bloqueada.")
            current_fingerprint = self._account_fingerprint(account)
            if self.requires_account_fingerprint and (
                expected_account_fingerprint is None
                or current_fingerprint is None
                or current_fingerprint != expected_account_fingerprint
            ):
                return PositionCloseObservation(
                    unknown,
                    "a conta MT5 conectada não corresponde à conta registrada na abertura.",
                )
            if expected_account_fingerprint is not None and current_fingerprint != expected_account_fingerprint:
                return PositionCloseObservation(unknown, "impressão digital da conta MT5 divergente.")

            deal_fn = getattr(mt5, "history_deals_get", None)
            order_fn = getattr(mt5, "history_orders_get", None)
            positions_fn = getattr(mt5, "positions_get", None)
            if not callable(deal_fn) or not callable(positions_fn):
                return PositionCloseObservation(unknown, "MT5 não oferece histórico de negócios e posições para reconciliação.")

            opening_deals = deal_fn(ticket=target_ticket)
            if opening_deals is None:
                return PositionCloseObservation(unknown, "MT5 não confirmou o histórico do ticket de abertura.")
            position_ids = {
                int(getattr(deal, "position_id", 0) or 0)
                for deal in opening_deals
                if str(getattr(deal, "position_id", "")).isdigit()
                and int(getattr(deal, "position_id", 0) or 0) > 0
            }
            if not position_ids and callable(order_fn):
                opening_orders = order_fn(ticket=target_ticket)
                if opening_orders is None:
                    return PositionCloseObservation(unknown, "MT5 não confirmou o histórico da ordem de abertura.")
                position_ids = {
                    int(getattr(order, "position_id", 0) or 0)
                    for order in opening_orders
                    if str(getattr(order, "position_id", "")).isdigit()
                    and int(getattr(order, "position_id", 0) or 0) > 0
                }
            if len(position_ids) != 1:
                return PositionCloseObservation(unknown, "ticket não pôde ser associado a uma única posição MT5.")

            position_id = next(iter(position_ids))
            positions = positions_fn()
            if positions is None:
                return PositionCloseObservation(unknown, "MT5 não confirmou a lista de posições abertas.")
            owned_open = tuple(
                position for position in positions
                if int(getattr(position, "ticket", -1)) == position_id
                and int(getattr(position, "magic", -1)) == self.config.magic
            )
            if len(owned_open) == 1:
                return PositionCloseObservation(
                    PositionCloseObservationStatus.OPEN,
                    "posição do Controlador continua aberta no MT5; nenhuma nova ordem foi enviada.",
                )
            if len(owned_open) > 1:
                return PositionCloseObservation(unknown, "mais de uma posição corresponde à identidade MT5.")

            closing_deals = deal_fn(position=position_id)
            if closing_deals is None:
                return PositionCloseObservation(unknown, "MT5 não confirmou o histórico de fechamento da posição.")
            close_entries = {
                value for value in (
                    getattr(mt5, "DEAL_ENTRY_OUT", None),
                    getattr(mt5, "DEAL_ENTRY_OUT_BY", None),
                ) if value is not None
            }
            confirmed_closes = tuple(
                deal for deal in closing_deals
                if getattr(deal, "entry", None) in close_entries
                and int(getattr(deal, "magic", -1)) == self.config.magic
            )
            if confirmed_closes:
                return PositionCloseObservation(
                    PositionCloseObservationStatus.CLOSED,
                    "histórico MT5 confirma negócio de saída e a posição não está aberta.",
                )
            return PositionCloseObservation(
                unknown,
                "posição não aparece aberta, mas não há negócio de saída verificável no histórico.",
            )
        except Exception as exc:
            return PositionCloseObservation(
                unknown,
                f"falha ao consultar evidências MT5: {type(exc).__name__}",
            )
        finally:
            mt5.shutdown()

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"


class ICMarketsMT5RealAdapter(ICMarketsMT5DemoAdapter):
    requires_account_fingerprint = True
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
            return ExecutionResult(
                True,
                "ordem REAL enviada e confirmada pelo MT5.",
                result.external_id,
                result.account_fingerprint,
            )
        return result
