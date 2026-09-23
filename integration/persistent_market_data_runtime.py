from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataBoundary, BrokerMarketDataRequest


@dataclass(frozen=True)
class MarketDataRuntimeConfig:
    symbol: str = "EURUSD"
    timeframe: str = "5m"
    limit: int = 100
    poll_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol obrigatório")
        if not self.timeframe.strip():
            raise ValueError("timeframe obrigatório")
        if self.limit <= 0:
            raise ValueError("limit deve ser maior que zero")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds deve ser maior que zero")


class PersistentMarketDataRuntime:
    """Keeps broker market data flowing into the shared runtime without daily commands.

    The broker adapter remains read-only. Failure only makes market data unsafe;
    it never grants execution authority.
    """

    def __init__(
        self,
        boundary: BrokerMarketDataBoundary,
        state: MarketDataRuntimeState,
        config: MarketDataRuntimeConfig,
    ) -> None:
        self._boundary = boundary
        self._state = state
        self._config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_success: datetime | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="controlador-market-data",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, object]:
        report = self._state.status()
        with self._lock:
            return {
                **report,
                "runtime": "RUNNING" if self._thread is not None and self._thread.is_alive() else "STOPPED",
                "symbol": self._config.symbol,
                "timeframe": self._config.timeframe,
                "last_success": self._last_success.isoformat() if self._last_success else None,
                "last_error": self._last_error,
            }

    def _run(self) -> None:
        request = BrokerMarketDataRequest(
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
            limit=self._config.limit,
        )
        expected_interval = self._timeframe_seconds(self._config.timeframe)
        while not self._stop.is_set():
            try:
                snapshot = self._boundary.fetch(request)
                self._state.update(
                    snapshot,
                    now=datetime.now().astimezone(),
                    expected_interval_seconds=expected_interval,
                )
                with self._lock:
                    self._last_success = snapshot.received_at
                    self._last_error = None
            except Exception as exc:
                self._state.invalidate(
                    source=self._boundary._source if hasattr(self._boundary, "_source") else "market_data_provider",
                    symbol=self._config.symbol,
                    timeframe=self._config.timeframe,
                    message=f"falha ao atualizar dados de mercado: {type(exc).__name__}: {exc}",
                )
                with self._lock:
                    self._last_error = str(exc)
            self._stop.wait(self._config.poll_seconds)

    @staticmethod
    def _timeframe_seconds(timeframe: str) -> int | None:
        values = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
        return values.get(timeframe.strip().lower())
