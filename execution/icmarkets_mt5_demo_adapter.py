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

    def __post_init__(self) -> None:
        if self.symbol is not None and (not isinstance(self.symbol, str) or not self.symbol.strip()):
            raise ValueError("symbol inválido")
        if isinstance(self.deviation, bool) or not isinstance(self.deviation, int) or self.deviation < 0:
            raise ValueError("deviation inválido")
        if isinstance(self.magic, bool) or not isinstance(self.magic, int) or self.magic < 0:
            raise ValueError("magic inválido")


class ICMarketsMT5DemoAdapter:
    """IC Markets MT5 DEMO boundary."""

    def __init__(self, config: ICMarketsMT5DemoConfig | None = None, mt5_module: Any = None) -> None:
        self.config = config or ICMarketsMT5DemoConfig()
        self._mt5 = mt5_module

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5AdapterError("MetaTrader5 não instalado; este adapter precisa de um runtime com MT5.") from exc
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
        trade_mode = getattr(account, "trade_mode", None)
        if isinstance(demo_mode, bool) or not isinstance(demo_mode, int):
            return False
        if isinstance(trade_mode, bool) or not isinstance(trade_mode, int):
            return False
        return trade_mode == demo_mode

    @staticmethod
    def _valid_volume(amount: float, symbol_info: Any) -> bool:
        if not math.isfinite(amount) or amount <= 0:
            return False
        minimum = getattr(symbol_info, "volume_min", None)
        maximum = getattr(symbol_info, "volume_max", None)
        step = getattr(symbol_info, "volume_step", None)
        if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (minimum, maximum, step)):
            return False
        if minimum <= 0 or maximum < minimum or step <= 0 or amount < minimum or amount > maximum:
            return False
        steps = (amount - minimum) / step
        return math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9)

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "IC Markets MT5 adapter aceita somente DEMO.")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não pode gerar ordem.")
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return ExecutionResult(False, "sinal inválido; ordem bloqueada.")
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(False, "request_id obrigatório para execução DEMO.")
        if isinstance(request.duration_seconds, bool) or not isinstance(request.duration_seconds, int) or request.duration_seconds <= 0:
            return ExecutionResult(False, "duration_seconds inválido; ordem bloqueada.")
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return ExecutionResult(False, "símbolo da requisição inválido; ordem bloqueada.")
        if not math.isfinite(request.amount) or request.amount <= 0:
            return ExecutionResult(False, "volume/amount deve ser maior que zero e finito.")

        configured_symbol = self.config.symbol.strip() if isinstance(self.config.symbol, str) else None
        request_symbol = request.symbol.strip()
        if configured_symbol is not None and configured_symbol.upper() != request_symbol.upper():
            return ExecutionResult(False, "símbolo configurado no adapter difere do símbolo da requisição; ordem bloqueada.")
        symbol = configured_symbol or request_symbol

        mt5 = self._module()
        if not mt5.initialize():
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada como DEMO; ordem bloqueada.")
            selected = mt5.symbol_select(symbol, True)
            if not isinstance(selected, bool) or not selected:
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
            try:
                check = mt5.order_check(payload)
            except Exception as exc:
                raise MT5AdapterError("MT5 order_check terminou sem confirmação determinística") from exc
            check_retcode = getattr(check, "retcode", None) if check is not None else None
            if (
                check is None
                or isinstance(check_retcode, bool)
                or not isinstance(check_retcode, int)
                or check_retcode != 0
            ):
                return ExecutionResult(False, "order_check bloqueou a ordem.")
            try:
                result = mt5.order_send(payload)
            except Exception as exc:
                raise MT5AdapterError("MT5 order_send terminou sem confirmação determinística") from exc
            if result is None:
                raise MT5AdapterError("MT5 order_send sem confirmação determinística")
            retcode = getattr(result, "retcode", None)
            success_code = getattr(mt5, "TRADE_RETCODE_DONE", None)
            ambiguous_codes = {
                getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
                getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
                getattr(mt5, "TRADE_RETCODE_TIMEOUT", 10012),
            }
            if retcode in ambiguous_codes:
                raise MT5AdapterError(f"MT5 order_send retornou estado potencialmente executado sem confirmação terminal: retcode={retcode}")
            if success_code is None or retcode != success_code:
                return ExecutionResult(False, f"ordem rejeitada pelo MT5: retcode={retcode}")
            external_id = getattr(result, "order", None) or getattr(result, "deal", None)
            if isinstance(external_id, bool) or not isinstance(external_id, (int, str)):
                raise MT5AdapterError("MT5 aceitou a ordem, mas não forneceu identificador externo válido")
            if isinstance(external_id, int) and external_id <= 0:
                raise MT5AdapterError("MT5 aceitou a ordem, mas o identificador externo é inválido")
            if isinstance(external_id, str) and not external_id.strip():
                raise MT5AdapterError("MT5 aceitou a ordem, mas o identificador externo é vazio")
            return ExecutionResult(True, "ordem DEMO enviada e confirmada pelo MT5.", str(external_id))
        finally:
            try:
                mt5.shutdown()
            except Exception:
                # A transport cleanup failure must never turn a broker-confirmed
                # result into a false rejection. Any execution uncertainty is
                # already handled at the order_send boundary above.
                pass

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
