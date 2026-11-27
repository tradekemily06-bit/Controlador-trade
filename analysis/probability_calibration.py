"""Strict, out-of-sample probability calibration diagnostics.

This module evaluates forecasts; it does not invent probabilities or promote a
model automatically. Every result is isolated by symbol, timeframe, direction,
and model version. Simulated fills and manual study labels are not calibration
evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite, log
from typing import Iterable

from data.timeframes import normalize_timeframe


_ALLOWED_PROVENANCE = {"REAL_MARKET_DATA", "VERIFIED_REAL_EXECUTION"}


@dataclass(frozen=True)
class ProbabilityForecast:
    forecast_id: str
    symbol: str
    timeframe: str
    direction: str
    model_version: str
    probability: float
    outcome: bool
    forecast_at: str
    resolved_at: str
    provenance: str
    out_of_sample: bool


def _valid_probability(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        return False
    return isfinite(numeric) and 0.0 <= numeric <= 1.0


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    # 95% Wilson score interval, z = 1.959963984540054.
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (
        z
        * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5)
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def evaluate_probability_calibration(
    forecasts: Iterable[ProbabilityForecast],
    *,
    minimum_sample_count: int = 100,
    bin_count: int = 10,
) -> dict[str, dict[str, object]]:
    """Return diagnostics per exact context; never pool across contexts.

    minimum_sample_count is an explicit policy input, not a claim that 100
    observations alone prove calibration. Even after the threshold, the
    output remains EVALUATED_REQUIRES_REVIEW and exposes no approved chance.
    """
    if (
        isinstance(minimum_sample_count, bool)
        or not isinstance(minimum_sample_count, int)
        or minimum_sample_count < 2
    ):
        raise ValueError("minimum_sample_count must be an integer >= 2")
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or bin_count < 2:
        raise ValueError("bin_count must be an integer >= 2")

    groups: dict[tuple[str, str, str, str], list[ProbabilityForecast]] = {}
    seen_ids: set[str] = set()
    rejected = 0
    for item in forecasts:
        if not isinstance(item, ProbabilityForecast):
            rejected += 1
            continue
        if (
            not isinstance(item.forecast_id, str)
            or not item.forecast_id.strip()
            or item.forecast_id.strip() in seen_ids
            or not all(
                isinstance(value, str) and value.strip()
                for value in (item.symbol, item.timeframe, item.direction, item.model_version)
            )
            or item.direction.strip().upper() not in {"COMPRA", "VENDA"}
            or not isinstance(item.outcome, bool)
            or not isinstance(item.out_of_sample, bool)
            or not item.out_of_sample
            or not isinstance(item.provenance, str)
            or item.provenance not in _ALLOWED_PROVENANCE
            or not isinstance(item.forecast_at, str)
            or not isinstance(item.resolved_at, str)
            or not _valid_probability(item.probability)
        ):
            rejected += 1
            continue
        try:
            if _utc(item.forecast_at) >= _utc(item.resolved_at):
                rejected += 1
                continue
        except (TypeError, ValueError):
            rejected += 1
            continue
        try:
            canonical_timeframe = normalize_timeframe(item.timeframe)
        except ValueError:
            rejected += 1
            continue
        seen_ids.add(item.forecast_id.strip())
        key = (
            item.symbol.strip().upper(),
            canonical_timeframe,
            item.direction.strip().upper(),
            item.model_version.strip(),
        )
        groups.setdefault(key, []).append(item)

    results: dict[str, dict[str, object]] = {}
    for (symbol, timeframe, direction, model_version), items in sorted(groups.items()):
        n = len(items)
        key = f"{symbol}|{timeframe}|{direction}|{model_version}"
        if n < minimum_sample_count:
            results[key] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "model_version": model_version,
                "sample_count": n,
                "calibration_status": "INSUFFICIENT_SAMPLE",
                "probability_of_profit": None,
                "brier_score": None,
                "log_loss": None,
                "reliability_bins": [],
                "rejected_records": rejected,
                "rejected_records_total": rejected,
            }
            continue

        brier = sum((float(x.probability) - float(x.outcome)) ** 2 for x in items) / n
        eps = 1e-15
        log_loss = -sum(
            float(x.outcome) * log(max(eps, min(1 - eps, float(x.probability))))
            + (1 - float(x.outcome)) * log(max(eps, min(1 - eps, 1 - float(x.probability))))
            for x in items
        ) / n
        bins: list[dict[str, object]] = []
        for index in range(bin_count):
            lower = index / bin_count
            upper = (index + 1) / bin_count
            bucket = [
                x for x in items
                if lower <= float(x.probability) < upper
                or (index == bin_count - 1 and float(x.probability) == 1.0)
            ]
            if not bucket:
                continue
            observed = sum(bool(x.outcome) for x in bucket)
            low, high = _wilson_interval(observed, len(bucket))
            bins.append({
                "lower_bound": lower,
                "upper_bound": upper,
                "sample_count": len(bucket),
                "mean_predicted_probability": sum(float(x.probability) for x in bucket) / len(bucket),
                "observed_success_rate": observed / len(bucket),
                "observed_rate_95ci": [low, high],
            })
        expected_calibration_error = sum(
            bucket["sample_count"]
            / n
            * abs(
                bucket["mean_predicted_probability"]
                - bucket["observed_success_rate"]
            )
            for bucket in bins
        )
        results[key] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "model_version": model_version,
            "sample_count": n,
            "calibration_status": "EVALUATED_REQUIRES_REVIEW",
            "probability_of_profit": None,
            "brier_score": brier,
            "log_loss": log_loss,
            "expected_calibration_error": expected_calibration_error,
            "reliability_bins": bins,
            "rejected_records": rejected,
            "rejected_records_total": rejected,
            "approval_note": (
                "Métricas fora da amostra calculadas; ainda exigem revisão de "
                "estabilidade, intervalos de confiança e critérios de aceitação."
            ),
        }
    return results
