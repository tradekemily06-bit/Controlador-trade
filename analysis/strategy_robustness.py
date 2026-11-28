"""Out-of-sample strategy robustness diagnostics.

Adapted from the research-validation approach in OpenTerminalUI's
robustness scorecard (MIT; Copyright 2026 OpenTerminalUI Contributors).
This implementation is independent and uses only the Python standard library.

This is a diagnostic, not a profitability guarantee, forecast, or execution gate.
Returns supplied to this function must already be out-of-sample and net of
realistic transaction costs. The function cannot verify those claims itself.
"""
from __future__ import annotations

import math
import random
from typing import Iterable


_EULER_GAMMA = 0.5772156649


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_ppf(probability: float) -> float:
    """Acklam rational approximation to the inverse standard normal CDF."""
    p = min(max(float(probability), 1e-12), 1.0 - 1e-12)
    a = (-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239)
    b = (-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572)
    c = (-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
         -2.549732539343734, 4.374664141464968, 2.938163982698783)
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996,
         3.754408661907416)
    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= 0.97575:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _sample_skew(values: list[float], mean: float, std: float) -> float:
    n = len(values)
    if n < 3 or std <= 0:
        return 0.0
    return (n / ((n - 1) * (n - 2))) * sum(((x - mean) / std) ** 3 for x in values)


def _sample_excess_kurtosis(values: list[float], mean: float, std: float) -> float:
    n = len(values)
    if n < 4 or std <= 0:
        return 0.0
    z4_sum = sum(((x - mean) / std) ** 4 for x in values)
    return (
        (n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))) * z4_sum
        - (3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    )


def _sharpe_variance_numerator(sharpe: float, skew: float, excess_kurtosis: float) -> float:
    value = 1.0 - skew * sharpe + (excess_kurtosis / 4.0) * sharpe**2
    if not math.isfinite(value):
        return 0.0
    return max(value, 0.0)


def _psr(sharpe: float | None, benchmark: float, n: int, skew: float, excess_kurtosis: float) -> float | None:
    if sharpe is None or n < 2:
        return None
    variance_numerator = _sharpe_variance_numerator(sharpe, skew, excess_kurtosis)
    if variance_numerator <= 0:
        return 1.0 if sharpe > benchmark else 0.0 if sharpe < benchmark else 0.5
    z_score = (sharpe - benchmark) * math.sqrt(n - 1) / math.sqrt(variance_numerator)
    return _normal_cdf(z_score)


def _deflated_benchmark(variance: float, trials: int) -> float:
    if trials <= 1:
        return 0.0
    p1 = 1.0 - 1.0 / trials
    p2 = 1.0 - 1.0 / (trials * math.e)
    expected_max = (1.0 - _EULER_GAMMA) * _normal_ppf(p1) + _EULER_GAMMA * _normal_ppf(p2)
    return math.sqrt(max(variance, 0.0)) * expected_max


def _annual_sharpe(values: list[float], periods_per_year: int) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return mean / std * math.sqrt(periods_per_year) if std > 0 else None


def _max_drawdown(values: list[float]) -> float | None:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in values:
        equity *= 1.0 + value
        if equity <= 0:
            return -1.0
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def _block_bootstrap_sharpe(
    values: list[float], *, paths: int, block_size: int, periods_per_year: int, seed: int
) -> dict[str, float | int | None]:
    if paths == 0 or len(values) < 2:
        return {"paths": 0, "ci_low": None, "ci_high": None, "p_positive": None}
    rng = random.Random(seed)
    n = len(values)
    sharpes: list[float] = []
    for _ in range(paths):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            for offset in range(block_size):
                sample.append(values[(start + offset) % n])
                if len(sample) == n:
                    break
        sharpe = _annual_sharpe(sample, periods_per_year)
        if sharpe is not None and math.isfinite(sharpe):
            sharpes.append(sharpe)
    return {
        "paths": len(sharpes),
        "ci_low": _percentile(sharpes, 0.025),
        "ci_high": _percentile(sharpes, 0.975),
        "p_positive": sum(value > 0 for value in sharpes) / len(sharpes) if sharpes else None,
    }


def evaluate_strategy_robustness(
    returns: Iterable[float],
    *,
    benchmark_returns: Iterable[float] | None,
    num_trials: int,
    periods_per_year: int,
    out_of_sample: bool,
    costs_included: bool,
    bootstrap_paths: int = 500,
    block_size: int = 10,
    seed: int = 42,
) -> dict[str, object]:
    """Evaluate one strategy's OOS net returns; never promotes it automatically."""
    if isinstance(num_trials, bool) or not isinstance(num_trials, int) or num_trials < 1:
        raise ValueError("num_trials must be an integer >= 1")
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year < 1:
        raise ValueError("periods_per_year must be an integer >= 1")
    if not isinstance(out_of_sample, bool) or not isinstance(costs_included, bool):
        raise ValueError("out_of_sample and costs_included must be booleans")
    if isinstance(bootstrap_paths, bool) or not isinstance(bootstrap_paths, int) or not 0 <= bootstrap_paths <= 10000:
        raise ValueError("bootstrap_paths must be an integer from 0 to 10000")
    if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
        raise ValueError("block_size must be a positive integer")
    values: list[float] = []
    for value in returns:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("returns must contain only finite numeric values")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= -1.0:
            raise ValueError("returns must be finite and greater than -100%")
        values.append(numeric)

    n = len(values)
    benchmark: list[float] = []
    if benchmark_returns is not None:
        for value in benchmark_returns:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("benchmark_returns must contain only finite numeric values")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric <= -1.0:
                raise ValueError("benchmark_returns must be finite and greater than -100%")
            benchmark.append(numeric)
        if len(benchmark) != n:
            raise ValueError("benchmark_returns must align one-to-one with strategy returns")
    base: dict[str, object] = {
        "sample_count": n,
        "num_trials": num_trials,
        "periods_per_year": periods_per_year,
        "out_of_sample": out_of_sample,
        "costs_included": costs_included,
        "bootstrap": {"paths": 0, "ci_low": None, "ci_high": None, "p_positive": None},
        "probabilistic_sharpe_ratio": None,
        "deflated_sharpe_ratio": None,
        "annualized_sharpe": None,
        "rolling_positive_sharpe_fraction": None,
        "max_drawdown": _max_drawdown(values) if values else None,
        "benchmark_sample_count": len(benchmark),
        "benchmark_total_return": math.prod(1.0 + x for x in benchmark) - 1.0 if benchmark else None,
        "strategy_total_return": math.prod(1.0 + x for x in values) - 1.0 if values else None,
        "benchmark_annualized_sharpe": _annual_sharpe(benchmark, periods_per_year) if benchmark else None,
        "verdict": "INSUFFICIENT",
        "reasons": [],
        "promotion_allowed": False,
    }
    if not out_of_sample:
        base["reasons"] = ["Only untouched out-of-sample returns are eligible."]
        return base
    if not costs_included:
        base["reasons"] = ["Transaction costs, spread and slippage must be included before robustness can be assessed."]
        return base
    if not benchmark:
        base["reasons"] = ["An aligned untouched out-of-sample benchmark is required."]
        return base
    if n < 60:
        base["reasons"] = ["Fewer than 60 out-of-sample periods; statistical estimates are unstable."]
        return base

    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    period_sharpe = mean / std if std > 0 else None
    annual_sharpe = period_sharpe * math.sqrt(periods_per_year) if period_sharpe is not None else None
    skew = _sample_skew(values, mean, std)
    excess_kurtosis = _sample_excess_kurtosis(values, mean, std)
    benchmark_period_sharpe = (sum(benchmark) / len(benchmark)) / (math.sqrt(sum((x - sum(benchmark) / len(benchmark)) ** 2 for x in benchmark) / (len(benchmark) - 1)) if len(benchmark) > 1 else 0.0) if len(benchmark) > 1 else None
    if benchmark_period_sharpe is None:
        base["reasons"] = ["Benchmark needs at least two aligned out-of-sample returns."]
        return base
    psr = _psr(period_sharpe, benchmark_period_sharpe, n, skew, excess_kurtosis)
    variance_numerator = _sharpe_variance_numerator(period_sharpe, skew, excess_kurtosis) if period_sharpe is not None else None
    sharpe_variance = variance_numerator / (n - 1) if variance_numerator is not None else None
    deflated_benchmark = _deflated_benchmark(sharpe_variance, num_trials) if sharpe_variance is not None else None
    dsr = _psr(period_sharpe, deflated_benchmark, n, skew, excess_kurtosis) if deflated_benchmark is not None else None
    bootstrap = _block_bootstrap_sharpe(
        values, paths=bootstrap_paths, block_size=block_size,
        periods_per_year=periods_per_year, seed=seed,
    )

    window = max(2, min(63, n // 4))
    rolling = [
        _annual_sharpe(values[start:start + window], periods_per_year)
        for start in range(0, n - window + 1)
    ]
    rolling = [value for value in rolling if value is not None and math.isfinite(value)]
    positive_fraction = sum(value > 0 for value in rolling) / len(rolling) if rolling else None

    reasons: list[str] = []
    if annual_sharpe is not None and annual_sharpe > 1.0 and dsr is not None and dsr < 0.5:
        verdict = "OVERFIT"
        reasons.append("High annualized Sharpe but weak deflated Sharpe confidence after accounting for strategy trials.")
    elif (
        psr is not None and psr >= 0.95
        and bootstrap["ci_low"] is not None and bootstrap["ci_low"] > 0.0
        and (num_trials == 1 or (dsr is not None and dsr >= 0.90))
        and positive_fraction is not None and positive_fraction >= 0.60
    ):
        verdict = "ROBUST_REQUIRES_REVIEW"
        reasons.append("Statistical diagnostics passed; independent review and regime/cost checks are still required.")
    else:
        verdict = "FRAGILE"
        if psr is None or psr < 0.95:
            reasons.append("Probabilistic Sharpe confidence is below 0.95.")
        if bootstrap["ci_low"] is None or bootstrap["ci_low"] <= 0:
            reasons.append("Block-bootstrap Sharpe interval includes or falls below zero.")
        if num_trials > 1 and (dsr is None or dsr < 0.90):
            reasons.append("Deflated Sharpe confidence is below 0.90 after accounting for trials.")
        if positive_fraction is None or positive_fraction < 0.60:
            reasons.append("Positive Sharpe stability is below 60% of rolling windows.")

    base.update({
        "annualized_sharpe": annual_sharpe,
        "benchmark_period_sharpe": benchmark_period_sharpe,
        "benchmark_annualized_sharpe": benchmark_period_sharpe * math.sqrt(periods_per_year),
        "probabilistic_sharpe_ratio": psr,
        "deflated_sharpe_ratio": dsr,
        "sharpe_variance": sharpe_variance,
        "bootstrap": bootstrap,
        "rolling_window": window,
        "rolling_window_count": len(rolling),
        "rolling_positive_sharpe_fraction": positive_fraction,
        "skew": skew,
        "excess_kurtosis": excess_kurtosis,
        "verdict": verdict,
        "reasons": reasons,
    })
    return base
