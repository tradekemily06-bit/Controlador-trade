from __future__ import annotations

from execution.mt5_demo_execution_gate import evaluate_execution_gate
from execution.mt5_demo_runtime_preflight import MT5RuntimePreflight


def valid_preflight(**overrides) -> MT5RuntimePreflight:
    values = {
        "available": True,
        "demo": True,
        "symbol": "EURUSD",
        "bid": 1.16065,
        "ask": 1.16066,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "message": "ok",
    }
    values.update(overrides)
    return MT5RuntimePreflight(**values)


def test_gate_allows_only_valid_demo_preflight() -> None:
    result = evaluate_execution_gate(valid_preflight())
    assert result.allowed is True


def test_gate_rejects_unavailable_preflight() -> None:
    result = evaluate_execution_gate(valid_preflight(available=False))
    assert result.allowed is False


def test_gate_rejects_invalid_quote() -> None:
    result = evaluate_execution_gate(valid_preflight(bid=1.2, ask=1.1))
    assert result.allowed is False
    assert "cotação inválida" in result.reason


def test_gate_rejects_invalid_volume_limits() -> None:
    result = evaluate_execution_gate(valid_preflight(volume_min=0, volume_step=0.01))
    assert result.allowed is False
    assert "limites de volume inválidos" in result.reason
