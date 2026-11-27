from __future__ import annotations

import pytest

from analysis.signal_outcome_resolver import resolve_next_candle_direction_safe


def signal(**changes):
    value = {
        "signal_id": "signal-1",
        "symbol": "EURUSD",
        "timeframe": "M1",
        "direction": "COMPRA",
        "candle_close_at": "2026-11-27T10:01:00Z",
        "observed_at": "2026-11-27T10:01:02Z",
        "valid_until": "2026-11-27T10:02:00Z",
    }
    value.update(changes)
    return value


def candle(**changes):
    value = {
        "symbol": "eurusd",
        "timeframe": "1m",
        "open_time": "2026-11-27T10:01:00Z",
        "open": 1.1500,
        "high": 1.1510,
        "low": 1.1490,
        "close": 1.1508,
    }
    value.update(changes)
    return value


def test_resolves_only_immediate_next_candle_and_marks_directional_hit():
    result = resolve_next_candle_direction_safe(
        signal(), candle(), provenance="REAL_MARKET_DATA"
    )
    assert result["outcome"] is True
    assert result["outcome_status"] == "DIRECTIONAL_HIT"
    assert result["timeframe"] == "1m"
    assert result["outcome_definition"] == "NEXT_CANDLE_CLOSE_VS_OPEN_DIRECTION_ONLY"
    assert result["net_profit_status"] == "NOT_ASSESSED"
    assert result["probability_of_profit"] is None
    assert result["calibration_eligible"] is False


def test_sell_direction_and_miss_are_directionally_correct():
    result = resolve_next_candle_direction_safe(
        signal(direction="VENDA"),
        candle(close=1.1508),
        provenance="REAL_MARKET_DATA",
    )
    assert result["outcome"] is False
    assert result["outcome_status"] == "DIRECTIONAL_MISS"


def test_doji_is_unresolved_not_win_or_loss():
    result = resolve_next_candle_direction_safe(
        signal(), candle(close=1.1500), provenance="REAL_MARKET_DATA"
    )
    assert result["outcome"] is None
    assert result["outcome_status"] == "UNRESOLVED_DOJI"


@pytest.mark.parametrize(
    "signal_changes,candle_changes",
    [
        ({}, {"timeframe": "M5"}),
        ({}, {"symbol": "GBPUSD"}),
        ({}, {"open_time": "2026-11-27T10:02:00Z"}),
        ({"valid_until": "2026-11-27T10:01:30Z"}, {}),
        ({"observed_at": "2026-11-27T10:00:59Z"}, {}),
        ({"timeframe": "M5"}, {}),
    ],
)
def test_rejects_wrong_symbol_timeframe_bar_or_expired_cycle(signal_changes, candle_changes):
    with pytest.raises(ValueError):
        resolve_next_candle_direction_safe(
            signal(**signal_changes), candle(**candle_changes),
            provenance="REAL_MARKET_DATA",
        )


def test_rejects_simulated_or_manual_provenance():
    with pytest.raises(ValueError):
        resolve_next_candle_direction_safe(
            signal(), candle(), provenance="SIMULATED_DEMO"
        )


@pytest.mark.parametrize(
    "values",
    [
        {"open": 1.2, "high": 1.1, "low": 1.0, "close": 1.05},
        {"open": 1.0, "high": 0.9, "low": 0.8, "close": 0.85},
        {"open": float("nan")},
        {"close": True},
    ],
)
def test_rejects_inconsistent_or_non_finite_ohlc(values):
    with pytest.raises(ValueError):
        resolve_next_candle_direction_safe(
            signal(), candle(**values), provenance="REAL_MARKET_DATA"
        )
