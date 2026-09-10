from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class MT5AdapterError(RuntimeError):
    """Raised when the MT5 runtime cannot be used safely."""


@dataclass(frozen=True)
class ICMarketsMT5DemoConfig:
    """Runtime configuration; credentials are intentionally not stored here."""

    symbol: str | None = None
    deviation: int = 20
    magic: int = 2609001


class ICMarketsMT5DemoAdapter:
    """IC Markets MT5 DEMO boundary.

    Uses the official MetaTrader5 Python package against a running MT5 terminal.
    The adapter stays outside decision/risk logic and rejects REAL requests.
    ``ExecutionRequest.amount`` is interpreted as MT5 volume (lots). MT5 has
    no fixed expiry here; positions remain open until explicitly closed.
    """

    def __init__(self, config: ICMarketsMT5DemoConfig | None = None, mt5_module: Any = None) -> None:
        self.config = config or ICMarketsMT5DemoConfig()
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
        try:
            mt5 = self._module()
            if not mt5.initialize():
                return False
            account = mt5.account_info()
            return account is not None and self._is_demo_account(account, mt5)
        except Exception:
            return False
        finally:
            if self._mt5 is not None:
                try:
                    self._mt5.shutdown()
                except Exception:
                    pass

    @staticmethod
    def _is_demo_account(account: Any, mt5: Any) -> bool:
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        return demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "IC Markets MT5 adapter aceita somente DEMO.")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não pode gerar ordem.")
        if request.amount <= 0:
            return ExecutionResult(False, "volume/amount deve ser maior que zero.")

        mt5 = self._module()
        if not mt5.initialize():
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada como DEMO; ordem bloqueada.")

            symbol = self.config.symbol or request.symbol
            if not mt5.symbol_select(symbol, True):
                return ExecutionResult(False, f"símbolo não disponível no MT5: {symbol}")

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return ExecutionResult(False, f"cotação indisponível para {symbol}.")

            is_buy = request.signal is Signal.COMPRA
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            price = tick.ask if is_buy else tick.bid
            payload = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(request.amount),
                "type": order_type,
                "price": price,
                "deviation": self.config.deviation,
                "magic": self.config.magic,
                "comment": "ControladorTrading-DEMO",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            check = mt5.order_check(payload)
            if check is None or getattr(check, "retcode", 0) != 0:
                return ExecutionResult(False, f"order_check bloqueou a ordem: {check}")

            result = mt5.order_send(payload)
            if result is None:
                return ExecutionResult(False, f"order_send sem confirmação: {self._last_error(mt5)}")

            retcode = getattr(result, "retcode", None)
            success_code = getattr(mt5, "TRADE_RETCODE_DONE", None)
            if success_code is None or retcode != success_code:
                return ExecutionResult(False, f"ordem rejeitada pelo MT5: retcode={retcode}")

            external_id = getattr(result, "order", None) or getattr(result, "deal", None)
            return ExecutionResult(
                True,
                "ordem DEMO enviada e confirmada pelo MT5.",
                str(external_id) if external_id is not None else None,
            )
        finally:
            mt5.shutdown()

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
