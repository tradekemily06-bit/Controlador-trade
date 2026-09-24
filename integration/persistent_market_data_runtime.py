from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataBoundary, BrokerMarketDataRequest, BrokerMarketDataSnapshot
from integration.market_data_candidate_sweep import MarketDataCandidateSweep


@dataclass(frozen=True)
class MarketDataRuntimeConfig:
    symbol: str | None = "EURUSD"
    timeframe: str = "5m"
    limit: int = 100
    poll_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.symbol is not None and not self.symbol.strip():
            raise ValueError("symbol não pode ser vazio quando informado")
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
        symbol_selector: Callable[[], str | None] | None = None,
        candidate_selector: Callable[[], Iterable[str]] | None = None,
        candidate_analyzer: Callable[[BrokerMarketDataSnapshot], object] | None = None,
    ) -> None:
        self._boundary = boundary
        self._state = state
        self._config = config
        self._symbol_selector = symbol_selector
        self._candidate_selector = candidate_selector
        self._candidate_analyzer = candidate_analyzer
        self._selected_symbol: str | None = config.symbol
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_success: datetime | None = None
        self._last_sweep_selected: str | None = None
        self._last_sweep_candidate_count = 0
        self._last_sweep_errors: tuple[str, ...] = ()

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
                "symbol": self._selected_symbol,
                "timeframe": self._config.timeframe,
                "last_success": self._last_success.isoformat() if self._last_success else None,
                "last_error": self._last_error,
                "candidate_sweep": {"enabled": self._candidate_selector is not None and self._candidate_analyzer is not None, "candidate_count": self._last_sweep_candidate_count, "selected_symbol": self._last_sweep_selected, "errors": list(self._last_sweep_errors)},
            }

    def _run(self) -> None:
        expected_interval = self._timeframe_seconds(self._config.timeframe)
        while not self._stop.is_set():
            if self._candidate_selector is not None and self._candidate_analyzer is not None:
                self._run_candidate_sweep()
                self._stop.wait(self._config.poll_seconds)
                continue
            symbol = self._resolve_symbol()
            if symbol is None:
                self._state.invalidate(
                    source=self._boundary.source,
                    symbol=self._selected_symbol or "AUTO",
                    timeframe=self._config.timeframe,
                    message="nenhum ativo MT5 elegível está disponível para análise",
                )
                self._stop.wait(self._config.poll_seconds)
                continue
            request = BrokerMarketDataRequest(
                symbol=symbol,
                timeframe=self._config.timeframe,
                limit=self._config.limit,
            )
            try:
                snapshot = self._boundary.fetch(request)
                with self._lock:
                    self._selected_symbol = symbol
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
                    source=self._boundary.source,
                    symbol=self._selected_symbol or 'AUTO',
                    timeframe=self._config.timeframe,
                    message=f"falha ao atualizar dados de mercado: {type(exc).__name__}: {exc}",
                )
                with self._lock:
                    self._last_error = str(exc)
            self._stop.wait(self._config.poll_seconds)

    def _run_candidate_sweep(self) -> None:
        candidates = tuple(dict.fromkeys(str(item).strip() for item in self._candidate_selector() if str(item).strip()))
        if not candidates:
            self._state.invalidate(source=self._boundary.source, symbol=self._selected_symbol or "AUTO", timeframe=self._config.timeframe, message="nenhum ativo candidato está disponível para análise")
            with self._lock:
                self._last_sweep_selected = None
                self._last_sweep_candidate_count = 0
                self._last_sweep_errors = ()
            return
        sweep = MarketDataCandidateSweep(boundary=self._boundary, state=self._state, timeframe=self._config.timeframe, limit=self._config.limit)
        result = sweep.sweep(candidates, analyzer=self._candidate_analyzer, is_actionable=self._is_actionable_result, rank_key=self._rank_analysis_result)
        errors = tuple(f"{item.symbol}: {item.error}" for item in result.candidates if item.error is not None)
        with self._lock:
            self._last_sweep_selected = result.selected_symbol
            self._last_sweep_candidate_count = len(result.candidates)
            self._last_sweep_errors = errors
            self._selected_symbol = result.selected_symbol
            if result.selected is not None and result.selected.snapshot is not None:
                self._last_success = result.selected.snapshot.received_at
                self._last_error = None
            elif errors:
                self._last_error = errors[-1]

    @staticmethod
    def _is_actionable_result(result: object) -> bool:
        signal = getattr(result, "signal", None)
        return getattr(signal, "value", signal) in {"COMPRA", "VENDA"} and bool(getattr(result, "confirmed", False))

    @staticmethod
    def _rank_analysis_result(result: object) -> tuple[int, float]:
        signal = getattr(result, "signal", None)
        value = getattr(signal, "value", signal)
        score = float(getattr(result, "score", 0))
        strength = score if value == "COMPRA" else 100.0 - score if value == "VENDA" else 0.0
        return (0 if value in {"COMPRA", "VENDA"} else 1, -strength)

    def _resolve_symbol(self) -> str | None:
        if self._symbol_selector is None:
            return self._config.symbol.strip() if self._config.symbol else None
        try:
            selected = self._symbol_selector()
        except Exception as exc:
            with self._lock:
                self._last_error = f"falha ao selecionar ativo: {type(exc).__name__}: {exc}"
            return None
        if selected is None:
            return None
        selected = str(selected).strip()
        return selected or None

    @staticmethod
    def _timeframe_seconds(timeframe: str) -> int | None:
        values = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
        return values.get(timeframe.strip().lower())
