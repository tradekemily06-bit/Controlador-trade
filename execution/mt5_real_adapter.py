from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any
import threading

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class MT5RealAdapterError(RuntimeError):
    """Raised when the configured MT5 terminal cannot be used safely for REAL."""


@dataclass(frozen=True)
class MT5RealConfig:
    """Non-secret runtime constraints for a REAL MT5 terminal.

    The adapter never stores passwords or account credentials. MetaTrader5
    connects through the terminal already configured on the machine.
    """

    symbol: str | None = None
    expected_server: str | None = None
    deviation: int = 20
    magic: int = 2609002
    comment: str = "ControladorTrading-REAL"

    def __post_init__(self) -> None:
        if self.symbol is not None and (not isinstance(self.symbol, str) or not self.symbol.strip()):
            raise ValueError("symbol inválido.")
        if self.expected_server is not None and (
            not isinstance(self.expected_server, str) or not self.expected_server.strip()
        ):
            raise ValueError("expected_server inválido.")
        if not isinstance(self.deviation, int) or isinstance(self.deviation, bool) or self.deviation < 0:
            raise ValueError("deviation inválido.")
        if not isinstance(self.magic, int) or isinstance(self.magic, bool) or self.magic < 0:
            raise ValueError("magic inválido.")
        if not isinstance(self.comment, str) or not self.comment.strip():
            raise ValueError("comment inválido.")


class MT5RealAdapter:
    """REAL MT5 execution boundary.

    Safety authority remains outside this adapter in RealExecutionGateway and
    the REAL admission/safety gates. This adapter only verifies that the
    connected terminal is a REAL account and sends the already-authorized
    request. It never accepts DEMO requests and never enables REAL by itself.
    """

    def __init__(self, config: MT5RealConfig | None = None, mt5_module: Any = None) -> None:
        self.config = config or MT5RealConfig()
        self._mt5 = mt5_module
        self._connected = False
        self._lock = threading.RLock()

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5RealAdapterError(
                    "MetaTrader5 não instalado; o terminal MT5 é necessário para execução REAL."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> bool:
        with self._lock:
            mt5 = self._module()
            if self._connected:
                return True
            self._connected = bool(mt5.initialize())
            return self._connected

    def disconnect(self) -> None:
        with self._lock:
            if self._connected:
                try:
                    self._module().shutdown()
                finally:
                    self._connected = False

    def is_available(self) -> bool:
        with self._lock:
            try:
                if not self.connect():
                    return False
                mt5 = self._module()
                account = mt5.account_info()
                if account is None or not self._is_real_account(account, mt5):
                    return False
                return self._server_matches(account)
            except Exception:
                self.disconnect()
                return False

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        with self._lock:
            return self._execute_locked(request)

    def _execute_locked(self, request: ExecutionRequest) -> ExecutionResult:
        if request.mode is not ExecutionMode.REAL:
            return ExecutionResult(False, "adapter MT5 REAL aceita somente requests REAL.")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não pode gerar ordem.")
        if not math.isfinite(request.amount) or request.amount <= 0:
            return ExecutionResult(False, "volume/amount deve ser maior que zero e finito.")

        if not self.connect():
            mt5 = self._module()
            return ExecutionResult(False, f"MT5 indisponível: {self._last_error(mt5)}")
        mt5 = self._module()

        try:
            account = mt5.account_info()
            if account is None or not self._is_real_account(account, mt5):
                return ExecutionResult(False, "conta MT5 não confirmada como REAL; ordem bloqueada.")
            if not self._server_matches(account):
                return ExecutionResult(False, "servidor MT5 não corresponde ao servidor REAL configurado.")

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
                "comment": self.config.comment,
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
                return ExecutionResult(False, f"ordem REAL rejeitada pelo MT5: retcode={retcode}")

            external_id = getattr(result, "order", None) or getattr(result, "deal", None)
            if external_id is None:
                return ExecutionResult(
                    False,
                    "MT5 aceitou a ordem, mas não forneceu identificador externo; confirmação bloqueada.",
                )

            return ExecutionResult(True, "ordem REAL enviada e confirmada pelo MT5.", str(external_id))
        finally:
            # PersistentBrokerConnectionRuntime owns disconnect/reconnect.
            pass

    def _server_matches(self, account: Any) -> bool:
        expected = self.config.expected_server
        if expected is None:
            return True
        actual = getattr(account, "server", None)
        return isinstance(actual, str) and actual.strip().lower() == expected.strip().lower()

    @staticmethod
    def _is_real_account(account: Any, mt5: Any) -> bool:
        real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", None)
        return real_mode is not None and getattr(account, "trade_mode", None) == real_mode

    @staticmethod
    def _valid_volume(amount: float, symbol_info: Any) -> bool:
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
        if minimum <= 0 or maximum < minimum or step <= 0 or amount < minimum or amount > maximum:
            return False
        steps = (amount - minimum) / step
        return math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9)

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
