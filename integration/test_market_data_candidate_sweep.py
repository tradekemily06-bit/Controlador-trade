from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataRequest
from data.models import Candle
from integration.market_data_candidate_sweep import MarketDataCandidateSweep


class _Provider:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.requests: list[str] = []

    def fetch_market_data(self, request: BrokerMarketDataRequest):
        self.requests.append(request.symbol)
        if request.symbol in self.failures:
            raise RuntimeError(f"provider failure for {request.symbol}")
            start = datetime.now(timezone.utc) - timedelta(minutes=150)
        offset = 100 if request.symbol == "WIN" else 0
        return [Candle(start + timedelta(minutes=5 * i), 100 + offset + i, 101 + offset + i, 99 + offset + i, 100.5 + offset + i) for i in range(30)]


def _sweep(provider: _Provider) -> MarketDataCandidateSweep:
    from core.p122_broker_market_data import BrokerMarketDataBoundary

    return MarketDataCandidateSweep(
        boundary=BrokerMarketDataBoundary(provider, source="test-provider"),
        state=MarketDataRuntimeState(MarketDataRuntimeIntegrity()),
        timeframe="5m",
        limit=30,
    )


def test_sweep_analyzes_candidates_and_leaves_winner_as_authoritative_snapshot() -> None:
    provider = _Provider()
    sweep = _sweep(provider)

    result = sweep.sweep(
        ["A", "WIN", "B"],
        analyzer=lambda snapshot: 100 if snapshot.symbol == "WIN" else 10,
        is_actionable=lambda value: value > 0,
        rank_key=lambda value: -value,
    )

    assert result.selected_symbol == "WIN"
    assert provider.requests == ["A", "WIN", "B"]
    assert result.selected is not None
    assert result.selected.result == 100
    snapshot = sweep._state.validated_snapshot_for_symbol(symbol="WIN")
    assert snapshot is not None
    assert snapshot.symbol == "WIN"


def test_sweep_does_not_poison_good_candidates_when_one_fetch_fails() -> None:
    provider = _Provider({"BROKEN"})
    sweep = _sweep(provider)

    result = sweep.sweep(
        ["BROKEN", "WIN"],
        analyzer=lambda snapshot: 50 if snapshot.symbol == "WIN" else 0,
        is_actionable=lambda value: value > 0,
        rank_key=lambda value: -value,
    )

    assert result.selected_symbol == "WIN"
    assert result.candidates[0].error is not None
    assert sweep._state.validated_snapshot_for_symbol(symbol="WIN") is not None


def test_sweep_invalidates_execution_context_when_no_candidate_is_actionable() -> None:
    provider = _Provider()
    sweep = _sweep(provider)

    result = sweep.sweep(
        ["A", "B"],
        analyzer=lambda snapshot: 0,
        is_actionable=lambda value: False,
        rank_key=lambda value: 0,
    )

    assert result.selected is None
    assert sweep._state.validated_snapshot_for_symbol(symbol="A") is None
    assert sweep._state.validated_snapshot_for_symbol(symbol="B") is None
    assert sweep._state.status()["safe_for_analysis"] is False


def test_sweep_deduplicates_candidates_and_keeps_broker_neutral_contract() -> None:
    provider = _Provider()
    sweep = _sweep(provider)

    result = sweep.sweep(
        ["A", "A", "  ", "B"],
        analyzer=lambda snapshot: 1,
        is_actionable=lambda value: True,
        rank_key=lambda value: 0,
    )

    assert [item.symbol for item in result.candidates] == ["A", "B"]
    assert provider.requests == ["A", "B"]
