from __future__ import annotations

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
        "1m": "TIMEFRAME_M1",
        "m1": "TIMEFRAME_M1",
        "5m": "TIMEFRAME_M5",
        "m5": "TIMEFRAME_M5",
        "15m": "TIMEFRAME_M15",
        "m15": "TIMEFRAME_M15",
        "30m": "TIMEFRAME_M30",
        "m30": "TIMEFRAME_M30",
        "1h": "TIMEFRAME_H1",
        "h1": "TIMEFRAME_H1",
        "4h": "TIMEFRAME_H4",
        "h4": "TIMEFRAME_H4",
        "1d": "TIMEFRAME_D1",
        "d1": "TIMEFRAME_D1",
    }

    def __init__(self, mt5_module: Any = None, terminal_path: str | None = None) -> None:
        self._mt5 = mt5_module
        self._terminal_path = terminal_path or os.environ.get("CONTROLADOR_MT5_TERMINAL_PATH") or None

    def initialize_terminal(self, mt5: Any) -> bool:
        initialized = bool(
            mt5.initialize(path=self._terminal_path, timeout=15_000)
            if self._terminal_path
            else mt5.initialize(timeout=15_000)
        )
        if not initialized:
            return False

        terminal = mt5.terminal_info()
        if terminal is None or not bool(getattr(terminal, "connected", False)):
            mt5.shutdown()
            raise MT5MarketDataError(
                "terminal MT5 não conectado após initialize; leitura bloqueada."
            )

        if self._terminal_path:
            expected = os.path.normcase(os.path.realpath(self._terminal_path))
            actual = os.path.normcase(
                os.path.realpath(
                    os.path.join(
                        getattr(terminal, "path", ""),
                        os.path.basename(self._terminal_path),
                    )
                )
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
        if not self.initialize_terminal(mt5):
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
