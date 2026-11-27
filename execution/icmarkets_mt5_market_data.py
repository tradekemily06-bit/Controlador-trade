from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from core.p122_broker_market_data import BrokerMarketDataPort, BrokerMarketDataRequest
from data.models import Candle
from data.normalizer import normalize_candle


class MT5MarketDataError(RuntimeError):
    """Raised when the MT5 market-data runtime cannot be used safely."""


class ICMarketsMT5DemoMarketDataAdapter(BrokerMarketDataPort):
    """Read-only IC Markets MT5 DEMO market-data adapter.

    It reads completed OHLCV bars from a running MT5 terminal and never
    places, modifies, or closes orders. The broker-specific details stay at
    the execution boundary; the core receives normalized Candle objects.
    """

    _TIMEFRAMES = {
        "1m": "TIMEFRAME_M1", "m1": "TIMEFRAME_M1",
        "2m": "TIMEFRAME_M2", "m2": "TIMEFRAME_M2",
        "3m": "TIMEFRAME_M3", "m3": "TIMEFRAME_M3",
        "4m": "TIMEFRAME_M4", "m4": "TIMEFRAME_M4",
        "5m": "TIMEFRAME_M5", "m5": "TIMEFRAME_M5",
        "6m": "TIMEFRAME_M6", "m6": "TIMEFRAME_M6",
        "10m": "TIMEFRAME_M10", "m10": "TIMEFRAME_M10",
        "12m": "TIMEFRAME_M12", "m12": "TIMEFRAME_M12",
        "15m": "TIMEFRAME_M15", "m15": "TIMEFRAME_M15",
        "20m": "TIMEFRAME_M20", "m20": "TIMEFRAME_M20",
        "30m": "TIMEFRAME_M30", "m30": "TIMEFRAME_M30",
        "1h": "TIMEFRAME_H1", "h1": "TIMEFRAME_H1",
        "2h": "TIMEFRAME_H2", "h2": "TIMEFRAME_H2",
        "3h": "TIMEFRAME_H3", "h3": "TIMEFRAME_H3",
        "4h": "TIMEFRAME_H4", "h4": "TIMEFRAME_H4",
        "6h": "TIMEFRAME_H6", "h6": "TIMEFRAME_H6",
        "8h": "TIMEFRAME_H8", "h8": "TIMEFRAME_H8",
        "12h": "TIMEFRAME_H12", "h12": "TIMEFRAME_H12",
        "1d": "TIMEFRAME_D1", "d1": "TIMEFRAME_D1",
        "1w": "TIMEFRAME_W1", "w1": "TIMEFRAME_W1",
    }
    def __init__(self, mt5_module: Any = None, terminal_path: str | None = None) -> None:
        self._mt5 = mt5_module
        self._terminal_path = terminal_path or os.environ.get("CONTROLADOR_MT5_TERMINAL_PATH") or None

    def _initialize(self, mt5: Any) -> bool:
        if not self._terminal_path:
            return bool(mt5.initialize())
        if not mt5.initialize(path=self._terminal_path):
            return False
        terminal = mt5.terminal_info()
        expected = os.path.normcase(os.path.realpath(self._terminal_path))
        actual = (
            os.path.normcase(
                os.path.realpath(
                    os.path.join(getattr(terminal, "path", ""), os.path.basename(self._terminal_path))
                )
            )
            if terminal is not None
            else ""
        )
        if actual != expected:
            mt5.shutdown()
            raise MT5MarketDataError(
                "terminal MT5 conectado não corresponde ao caminho configurado; leitura bloqueada."
            )
        return True

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5MarketDataError(
                    "MetaTrader5 não instalado; este adapter precisa de um runtime com MT5."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    @classmethod
    def supports_timeframe(cls, timeframe: str) -> bool:
        """Check native interval support without initializing or probing MT5."""
        from data.timeframes import normalize_timeframe

        try:
            normalized = normalize_timeframe(timeframe)
        except (TypeError, ValueError):
            return False
        return normalized in {key for key in cls._TIMEFRAMES if key[0].isdigit()}

    def _timeframe(self, timeframe: str) -> Any:
        key = timeframe.strip().lower().removeprefix("period_")
        constant_name = self._TIMEFRAMES.get(key)
        if constant_name is None:
            raise ValueError(f"timeframe não suportado: {timeframe}")
        mt5 = self._module()
        constant = getattr(mt5, constant_name, None)
        if constant is None:
            raise MT5MarketDataError(f"constante MT5 ausente: {constant_name}")
        return constant

    @staticmethod
    def _is_demo_account(account: Any, mt5: Any) -> bool:
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        return demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode

    def get_account_mode(self) -> str:
        """Return DEMO only after querying the currently connected terminal.

        REAL mode is deliberately not asserted by this DEMO-only adapter.
        Any missing terminal/account or unexpected mode fails closed.
        """
        mt5 = self._module()
        if not self._initialize(mt5):
            raise MT5MarketDataError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            terminal = mt5.terminal_info()
            if terminal is None or not bool(getattr(terminal, "connected", False)):
                raise MT5MarketDataError("terminal MT5 não está conectado")
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5MarketDataError("conta MT5 não confirmada como DEMO")
            return "DEMO"
        finally:
            mt5.shutdown()

    def get_account_reference(self) -> str:
        """Return a stable pseudonymous reference for the confirmed DEMO login/server."""
        mt5 = self._module()
        if not self._initialize(mt5):
            raise MT5MarketDataError(f"MT5 indisponível: {self._last_error(mt5)}")
        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            if terminal is None or not bool(getattr(terminal, "connected", False)):
                raise MT5MarketDataError("terminal MT5 não está conectado")
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5MarketDataError("conta MT5 não confirmada como DEMO")
            login = getattr(account, "login", None)
            server = getattr(account, "server", None)
            if isinstance(login, bool) or not isinstance(login, int) or login <= 0:
                raise MT5MarketDataError("login MT5 não pôde ser confirmado")
            if not isinstance(server, str) or not server.strip():
                raise MT5MarketDataError("servidor MT5 não pôde ser confirmado")
            digest = hashlib.sha256(f"{login}@{server.strip()}".encode("utf-8")).hexdigest()[:32]
            return "mt5_" + digest
        finally:
            mt5.shutdown()

    def fetch(self, request) -> tuple[Candle, ...]:
        """Adapt the generic core feed request to the broker-aware contract.

        This keeps one MT5 data source while allowing ``MarketDataFeed`` and
        ``TradingOrchestrator`` to consume it without introducing another
        market-data interface.
        """
        from data.feed import MarketDataRequest

        if not isinstance(request, MarketDataRequest):
            raise TypeError("request deve ser MarketDataRequest")
        broker_request = BrokerMarketDataRequest(
            symbol=request.symbol,
            timeframe=request.timeframe,
            limit=request.limit,
        )
        return self.fetch_market_data(broker_request)

    def fetch_market_data(self, request: BrokerMarketDataRequest) -> tuple[Candle, ...]:
        if not isinstance(request, BrokerMarketDataRequest):
            raise TypeError("request deve ser BrokerMarketDataRequest")

        mt5 = self._module()
        timeframe = self._timeframe(request.timeframe)
        if not self._initialize(mt5):
            raise MT5MarketDataError(f"MT5 indisponível: {self._last_error(mt5)}")

        try:
            account = mt5.account_info()
            if account is None or not self._is_demo_account(account, mt5):
                raise MT5MarketDataError("conta MT5 não confirmada como DEMO; leitura bloqueada.")

            if not mt5.symbol_select(request.symbol, True):
                raise MT5MarketDataError(f"símbolo não disponível no MT5: {request.symbol}")

            # start_pos=1 excludes the currently forming candle so analysis
            # never treats an unfinished bar as a confirmed candle.
            rates = mt5.copy_rates_from_pos(request.symbol, timeframe, 1, request.limit)
            if rates is None:
                raise MT5MarketDataError(
                    f"dados indisponíveis para {request.symbol}: {self._last_error(mt5)}"
                )

            candles: list[Candle] = []
            for rate in rates:
                timestamp = datetime.fromtimestamp(int(rate["time"]), tz=timezone.utc)
                volume = rate["tick_volume"]
                if volume is None:
                    volume = rate["real_volume"]
                candles.append(
                    normalize_candle(
                        timestamp=timestamp,
                        open=rate["open"],
                        high=rate["high"],
                        low=rate["low"],
                        close=rate["close"],
                        volume=volume,
                    )
                )

            return tuple(candles)
        finally:
            mt5.shutdown()

    @staticmethod
    def _last_error(mt5: Any) -> str:
        try:
            return str(mt5.last_error())
        except Exception:
            return "erro desconhecido"
