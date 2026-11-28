from __future__ import annotations

import math

import pytest

from analysis.strategy_robustness import evaluate_strategy_robustness


def _returns():
    pattern = (0.010, 0.012, 0.015, -0.002, 0.008)
    return pattern * 24


def _benchmark():
    pattern = (0.002, 0.003, 0.004, -0.001, 0.002)
    return pattern * 24


def _evaluate(**overrides):
    args = {
        "returns": _returns(),
        "benchmark_returns": _benchmark(),
        "num_trials": 1,
        "periods_per_year": 252,
        "out_of_sample": True,
        "costs_included": True,
        "bootstrap_paths": 120,
        "block_size": 5,
        "seed": 7,
    }
    args.update(overrides)
    return evaluate_strategy_robustness(**args)


def test_robustness_requires_untouched_out_of_sample_returns():
    result = _evaluate(out_of_sample=False)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["promotion_allowed"] is False
    assert "out-of-sample" in result["reasons"][0]


def test_robustness_requires_transaction_costs():
    result = _evaluate(costs_included=False)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["promotion_allowed"] is False
    assert "costs" in result["reasons"][0]


def test_robustness_requires_aligned_benchmark():
    result = evaluate_strategy_robustness(
        _returns(), benchmark_returns=None, num_trials=1,
        periods_per_year=252, out_of_sample=True, costs_included=True,
    )
    assert result["verdict"] == "INSUFFICIENT"
    assert "benchmark" in result["reasons"][0]


def test_robustness_rejects_misaligned_benchmark():
    with pytest.raises(ValueError):
        _evaluate(benchmark_returns=_benchmark()[:-1])


def test_robustness_rejects_non_finite_and_boolean_returns():
    with pytest.raises(ValueError):
        _evaluate(returns=[0.01, float("nan")])
    with pytest.raises(ValueError):
        _evaluate(returns=[0.01, True])


def test_robustness_rejects_return_at_or_below_total_loss():
    with pytest.raises(ValueError):
        _evaluate(returns=[0.01, -1.0])


def test_robustness_reports_auditable_metrics_without_granting_promotion():
    result = _evaluate()
    assert result["sample_count"] == 120
    assert result["num_trials"] == 1
    assert result["benchmark_sample_count"] == 120
    assert result["annualized_sharpe"] is not None
    assert result["probabilistic_sharpe_ratio"] is not None
    assert result["bootstrap"]["paths"] == 120
    assert result["rolling_window_count"] > 0
    assert result["promotion_allowed"] is False
    assert result["verdict"] in {"ROBUST_REQUIRES_REVIEW", "FRAGILE", "OVERFIT"}


def test_multiple_trials_reduce_or_preserve_not_inflate_deflated_confidence():
    single = _evaluate(num_trials=1)
    many = _evaluate(num_trials=50)
    assert single["deflated_sharpe_ratio"] is not None
    assert many["deflated_sharpe_ratio"] is not None
    assert many["deflated_sharpe_ratio"] <= single["deflated_sharpe_ratio"] + 1e-12


def test_bootstrap_is_reproducible_for_same_seed():
    first = _evaluate(seed=19)
    second = _evaluate(seed=19)
    assert first["bootstrap"] == second["bootstrap"]


def test_constant_benchmark_is_inconclusive_not_a_crash():
    result = _evaluate(benchmark_returns=[0.0] * 120)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["promotion_allowed"] is False
