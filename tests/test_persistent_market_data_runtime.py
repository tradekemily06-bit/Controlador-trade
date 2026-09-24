from __future__ import annotations

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from integration.persistent_market_data_runtime import MarketDataRuntimeConfig, PersistentMarketDataRuntime


class _Boundary:
    source = "test"

    def fetch(self, request):
        raise AssertionError("fetch não deve ser chamado neste teste")


def test_runtime_resolves_dynamic_symbol_when_no_fixed_symbol() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
        symbol_selector=lambda: "BTCUSD",
    )

    assert runtime._resolve_symbol() == "BTCUSD"
    assert runtime.status()["symbol"] is None


def test_runtime_fails_closed_when_dynamic_selector_returns_no_symbol() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
        symbol_selector=lambda: None,
    )

    assert runtime._resolve_symbol() is None


def test_runtime_can_configure_provider_neutral_candidate_analysis_before_start() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    runtime = PersistentMarketDataRuntime(
        _Boundary(),
        state,
        MarketDataRuntimeConfig(symbol=None, timeframe="5m", limit=100, poll_seconds=1),
    )
    runtime.configure_candidate_analysis(
        candidate_selector=lambda: ("EURUSD", "GBPUSD"),
        candidate_analyzer=lambda snapshot: snapshot,
    )
    status = runtime.status()
    assert status["candidate_sweep"]["enabled"] is True
    assert status["candidate_sweep"]["candidate_count"] == 0
