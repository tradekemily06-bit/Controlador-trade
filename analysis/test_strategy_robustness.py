from __future__ import annotations

import math

import pytest

from analysis.strategy_robustness import (
    _deflated_benchmark,
    _normal_ppf,
    analyze_backtest_overfitting,
    _sharpe_variance_numerator,
    evaluate_strategy_robustness,
)


def _returns():
    pattern = (0.010, 0.012, 0.015, -0.002, 0.008)
    return pattern * 24


def _benchmark():
    pattern = (0.002, 0.003, 0.004, -0.001, 0.002)
    return pattern * 24


def _selection_returns():
    pattern = (0.006, 0.008, 0.009, -0.001, 0.005)
    return pattern * 24


def _period_sharpe(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean / math.sqrt(variance)


def _evaluate(**overrides):
    args = {
        "returns": _returns(),
        "benchmark_returns": _benchmark(),
        "stress_returns": (0.003, 0.004, 0.005, -0.0005, 0.003) * 24,
        "selection_returns": _selection_returns(),
        "selection_trial_sharpes": [_period_sharpe(_selection_returns())],
        "selected_trial_index": 0,
        "trade_count": 48,
        "stress_cost_multiplier": 2.0,
        "num_trials": 1,
        "periods_per_year": 252,
        "out_of_sample": True,
        "costs_included": True,
        "bootstrap_paths": 120,
        "block_size": 5,
        "seed": 7,
    }
    args.update(overrides)
    if "selection_trial_sharpes" not in overrides and args["selection_returns"] is not None:
        selected_sr = _period_sharpe(args["selection_returns"])
        args["selection_trial_sharpes"] = [selected_sr - 0.01 * (args["num_trials"] - 1 - i) for i in range(args["num_trials"])]
    if "selected_trial_index" not in overrides:
        args["selected_trial_index"] = args["num_trials"] - 1
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
        _returns(), benchmark_returns=None, stress_returns=None, selection_returns=None, selection_trial_sharpes=None, selected_trial_index=0, trade_count=48, stress_cost_multiplier=2.0, num_trials=1,
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
    assert result["selection_trial_count"] == 1
    assert result["selection_period_count"] == 120
    assert result["selection_period_sharpe"] == pytest.approx(_period_sharpe(_selection_returns()))
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
    assert many["selection_trial_count"] == 50
    assert many["deflated_sharpe_ratio"] <= single["deflated_sharpe_ratio"] + 1e-12


def test_bootstrap_is_reproducible_for_same_seed():
    first = _evaluate(seed=19)
    second = _evaluate(seed=19)
    assert first["bootstrap"] == second["bootstrap"]


def test_constant_benchmark_is_inconclusive_not_a_crash():
    result = _evaluate(benchmark_returns=[0.0] * 120)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["promotion_allowed"] is False


def test_robustness_requires_a_two_times_cost_stress_run():
    result = _evaluate(stress_returns=None)
    assert result["verdict"] == "INSUFFICIENT"
    assert "2x" in result["reasons"][0]


def test_robustness_requires_at_least_thirty_completed_trades():
    result = _evaluate(trade_count=29)
    assert result["verdict"] == "INSUFFICIENT"
    assert "30" in result["reasons"][0]


def test_cost_stress_multiplier_must_be_at_least_two():
    with pytest.raises(ValueError):
        _evaluate(stress_cost_multiplier=1.5)


def test_psr_uses_non_excess_kurtosis_convention():
    # For Gaussian returns, excess kurtosis is zero and non-excess kurtosis is three.
    assert _sharpe_variance_numerator(2.0, 0.0, 0.0) == pytest.approx(3.0)


def test_deflated_benchmark_uses_cross_trial_sharpe_dispersion():
    expected_max = (1.0 - 0.5772156649) * _normal_ppf(0.5) + 0.5772156649 * _normal_ppf(1.0 - 1.0 / (2.0 * math.e))
    assert _deflated_benchmark([0.5, 1.5]) == pytest.approx(math.sqrt(0.5) * expected_max)
    assert _deflated_benchmark([1.0, 1.0]) == pytest.approx(0.0)


def test_dsr_refuses_to_guess_missing_selection_trial_results():
    result = _evaluate(selection_trial_sharpes=None)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["deflated_sharpe_ratio"] is None
    assert "every strategy trial" in result["reasons"][0]


def test_dsr_requires_exactly_one_selection_sharpe_per_trial():
    with pytest.raises(ValueError):
        _evaluate(num_trials=3, selection_trial_sharpes=[0.4, 0.5])



def test_cscv_backtest_overfitting_reports_all_combinatorial_splits():
    matrix = [
        [
            0.001 * ((row % 7) - 3) + 0.0002 * (row % 3),
            0.0008 * ((row % 5) - 2),
            0.0005 * ((row % 9) - 4) + 0.0001,
        ]
        for row in range(80)
    ]
    result = analyze_backtest_overfitting(matrix, n_blocks=8)
    assert result["method"] == "CSCV"
    assert result["split_count"] == 70
    assert 0.0 <= result["pbo"] <= 1.0
    assert 0.0 <= result["probability_oos_loss"] <= 1.0
    assert sum(result["selection_frequency"]) == 70
    assert result["strategy_count"] == 3


def test_cscv_identical_zero_strategies_are_tied_not_falsely_profitable():
    result = analyze_backtest_overfitting([[0.0, 0.0] for _ in range(8)], n_blocks=8)
    assert result["pbo"] == 1.0
    assert result["probability_oos_loss"] == 0.0
    assert result["selection_frequency"] == [70, 0]


def test_cscv_rejects_ragged_or_non_finite_matrices():
    with pytest.raises(ValueError):
        analyze_backtest_overfitting([[0.01, 0.02], [0.01]], n_blocks=8)
    with pytest.raises(ValueError):
        analyze_backtest_overfitting([[0.01, float("nan")] for _ in range(8)], n_blocks=8)


def test_cscv_rejects_unsupported_block_counts_and_non_divisible_periods():
    with pytest.raises(ValueError):
        analyze_backtest_overfitting([[0.01, 0.02] for _ in range(8)], n_blocks=7)
    with pytest.raises(ValueError):
        analyze_backtest_overfitting([[0.01, 0.02] for _ in range(9)], n_blocks=8)


def test_dsr_uses_selection_period_not_the_untouched_oos_sample():
    result = _evaluate()
    assert result["selection_period_sharpe"] == pytest.approx(_period_sharpe(_selection_returns()))
    assert result["annualized_sharpe"] == pytest.approx(_period_sharpe(_returns()) * math.sqrt(252))


def test_dsr_requires_selected_strategy_to_be_selection_sharpe_winner():
    result = _evaluate(selected_trial_index=0, num_trials=3)
    assert result["verdict"] == "INSUFFICIENT"
    assert "selection-period Sharpe winner" in result["reasons"][0]


def test_dsr_rejects_trial_sharpe_that_does_not_match_selected_selection_returns():
    with pytest.raises(ValueError):
        _evaluate(selection_trial_sharpes=[0.25])


def test_dsr_requires_separate_selection_period_sample():
    result = _evaluate(selection_returns=None)
    assert result["verdict"] == "INSUFFICIENT"
    assert "selection-period" in result["reasons"][0]


def test_dsr_allows_selected_strategy_tied_for_best_selection_sharpe():
    selected = _period_sharpe(_selection_returns())
    result = _evaluate(
        num_trials=2,
        selection_trial_sharpes=[selected, selected],
        selected_trial_index=1,
    )
    assert result["selection_trial_count"] == 2
    assert result["deflated_sharpe_ratio"] is not None
