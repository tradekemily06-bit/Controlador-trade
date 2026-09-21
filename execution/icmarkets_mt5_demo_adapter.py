from __future__ import annotations

from dataclasses import dataclass
import math
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

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(False, "request_id obrigatório para execução DEMO.")
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

            requested_symbol = request.symbol.strip() if isinstance(request.symbol, str) else ""
            configured_symbol = self.config.symbol.strip() if isinstance(self.config.symbol, str) else None
            if configured_symbol is not None and configured_symbol != requested_symbol:
                return ExecutionResult(False, "símbolo configurado difere do símbolo da requisição; ordem bloqueada.")
            symbol = configured_symbol or requested_symbol
            if not symbol:
                return ExecutionResult(False, "símbolo inválido; ordem bloqueada.")
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
                "comment": "ControladorTrading-DEMO",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            check = mt5.order_check(payload)
            if check is None or getattr(check, "retcode", 0) != 0:
                return ExecutionResult(False, f"order_check bloqueou a ordem: {check}")

            try:
                result = mt5.order_send(payload)
            except Exception as exc:
                return ExecutionResult(
                    False,
                    f"order_send falhou após despacho potencial; resultado externo incerto: {type(exc).__name__}: {exc}",
                    ambiguous=True,
                )
            if result is None:
                return ExecutionResult(
                    False,
                    f"order_send sem confirmação; resultado externo incerto: {self._last_error(mt5)}",
                    ambiguous=True,
                )

            retcode = getattr(result, "retcode", None)
            success_code = getattr(mt5, "TRADE_RETCODE_DONE", None)
            ambiguous_codes = {
                getattr(mt5, "TRADE_RETCODE_PLACED", -1),
                getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1),
                getattr(mt5, "TRADE_RETCODE_TIMEOUT", -1),
                getattr(mt5, "TRADE_RETCODE_ORDER_CHANGED", -1),
                getattr(mt5, "TRADE_RETCODE_LOCKED", -1),
            }
            external_id = getattr(result, "order", None) or getattr(result, "deal", None)

            if retcode in ambiguous_codes:
                detail = "MT5 executou parte da ordem (execução parcial)" if retcode == getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None) else "MT5 retornou estado potencialmente externo/ambíguo"
                return ExecutionResult(
                    False,
                    f"{detail}: retcode={retcode}; reconciliação necessária.",
                    str(external_id) if external_id is not None else None,
                    ambiguous=True,
                )

            if success_code is None:
                return ExecutionResult(
                    False,
                    "MT5 não expôs TRADE_RETCODE_DONE; confirmação bloqueada.",
                    str(external_id) if external_id is not None else None,
                    ambiguous=True,
                )

            if retcode != success_code:
                return ExecutionResult(False, f"ordem rejeitada pelo MT5: retcode={retcode}")

            if external_id is None:
                return ExecutionResult(
                    False,
                    "MT5 aceitou a ordem, mas não forneceu identificador externo; estado externo incerto.",
                    ambiguous=True,
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
