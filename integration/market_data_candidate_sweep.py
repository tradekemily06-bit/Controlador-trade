from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataBoundary, BrokerMarketDataRequest, BrokerMarketDataSnapshot

T = TypeVar("T")


@dataclass(frozen=True)
class MarketDataCandidateResult(Generic[T]):
    """Result of analyzing one candidate through the shared market-data boundary."""

    symbol: str
    snapshot: BrokerMarketDataSnapshot | None
    result: T | None
    error: str | None = None


@dataclass(frozen=True)
class MarketDataCandidateSweepResult(Generic[T]):
    """Provider-neutral result of one sequential opportunity sweep."""

    candidates: tuple[MarketDataCandidateResult[T], ...]
    selected: MarketDataCandidateResult[T] | None

    @property
    def selected_symbol(self) -> str | None:
        return self.selected.symbol if self.selected is not None else None


class MarketDataCandidateSweep(Generic[T]):
    """Fetch, validate, analyze and select candidates through one shared runtime state.

    This component is deliberately broker-neutral. A broker adapter enters only
    through BrokerMarketDataBoundary. The selected snapshot is the only snapshot
    left authoritative for subsequent execution validation.
    """

    def __init__(self, *, boundary: BrokerMarketDataBoundary, state: MarketDataRuntimeState, timeframe: str, limit: int) -> None:
        if not isinstance(boundary, BrokerMarketDataBoundary):
            raise TypeError("boundary deve ser BrokerMarketDataBoundary")
        if not isinstance(state, MarketDataRuntimeState):
            raise TypeError("state deve ser MarketDataRuntimeState")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("timeframe obrigatório")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit inválido")
        self._boundary = boundary
        self._state = state
        self._timeframe = timeframe.strip()
        self._limit = limit

    def sweep(self, candidates: Iterable[str], *, analyzer: Callable[[BrokerMarketDataSnapshot], T], is_actionable: Callable[[T], bool], rank_key: Callable[[T], object], now: datetime | None = None) -> MarketDataCandidateSweepResult[T]:
        if not callable(analyzer):
            raise TypeError("analyzer deve ser chamável")
        if not callable(is_actionable):
            raise TypeError("is_actionable deve ser chamável")
        if not callable(rank_key):
            raise TypeError("rank_key deve ser chamável")

        symbols: list[str] = []
        for value in candidates:
            symbol = str(value).strip()
            if symbol and symbol not in symbols:
                symbols.append(symbol)

        results: list[MarketDataCandidateResult[T]] = []
        successful_actionable: list[MarketDataCandidateResult[T]] = []

        for symbol in symbols:
            try:
                snapshot = self._boundary.fetch(
                    BrokerMarketDataRequest(symbol=symbol, timeframe=self._timeframe, limit=self._limit)
                )
                self._state.update(
                    snapshot,
                    now=now or datetime.now().astimezone(),
                    expected_interval_seconds=self._timeframe_seconds(self._timeframe),
                )
                result = analyzer(snapshot)
                item = MarketDataCandidateResult(symbol=symbol, snapshot=snapshot, result=result)
                results.append(item)
                if is_actionable(result):
                    successful_actionable.append(item)
            except Exception as exc:
                results.append(MarketDataCandidateResult(symbol=symbol, snapshot=None, result=None, error=f"{type(exc).__name__}: {exc}"))

        if not successful_actionable:
            self._state.invalidate(
                source=self._boundary.source,
                symbol="AUTO",
                timeframe=self._timeframe,
                message="nenhuma oportunidade candidata foi validada pelo sweep",
            )
            return MarketDataCandidateSweepResult(tuple(results), None)

        selected = min(successful_actionable, key=lambda item: rank_key(item.result))
        assert selected.snapshot is not None
        self._state.update(
            selected.snapshot,
            now=now or datetime.now().astimezone(),
            expected_interval_seconds=self._timeframe_seconds(self._timeframe),
        )
        return MarketDataCandidateSweepResult(tuple(results), selected)

    @staticmethod
    def _timeframe_seconds(timeframe: str) -> int | None:
        return {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe.strip().lower())
