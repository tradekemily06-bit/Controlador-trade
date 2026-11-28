"""Replay the repository's versioned technical pipeline on closed historical candles.

This is a research-only adapter: it generates historical decisions from the
in-repository StrategyPipeline, records the trial, and never authorizes orders.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence

from analysis.pipeline import StrategyPipeline
from data.models import Candle
from core.models import Signal

REGISTERED_STRATEGIES = {
    "technical-pipeline-v1": StrategyPipeline,
}
WARMUP_CANDLES = 30


def evaluate_registered_strategy_trial(
    *,
    ledger: Any,
    tenant_context: Any,
    phase: str,
    experiment_id: str,
    trial_id: str,
    strategy_version: str,
    dataset_id: str,
    candles_payload: Sequence[Mapping[str, Any]],
    take_profit_distance: float,
    stop_loss_distance: float,
) -> dict[str, Any]:
    """Generate decisions from a registered strategy, then reuse audited replay."""
    if strategy_version not in REGISTERED_STRATEGIES:
        raise ValueError("strategy_version is not registered in this application build")
    if not isinstance(candles_payload, (list, tuple)) or not WARMUP_CANDLES <= len(candles_payload) <= 50000:
        raise ValueError(f"candles must contain between {WARMUP_CANDLES} and 50000 records")

    candles: list[Candle] = []
    for index, row in enumerate(candles_payload):
        if not isinstance(row, Mapping):
            raise ValueError(f"candle {index} must be an object")
        raw_timestamp = row.get("timestamp")
        if not isinstance(raw_timestamp, str):
            raise ValueError(f"candles[{index}].timestamp must be ISO-8601 text")
        try:
            timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"candles[{index}].timestamp is invalid") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError(f"candles[{index}].timestamp must include a timezone")
        values = {key: row.get(key) for key in ("open", "high", "low", "close", "volume")}
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"candles[{index}].{key} must be a finite number")
        candle = Candle(timestamp=timestamp, **values)
        if not candle.is_valid():
            raise ValueError(f"candle {index} is invalid")
        if candles and timestamp <= candles[-1].timestamp:
            raise ValueError("candles must be strictly chronological without duplicates")
        candles.append(candle)

    pipeline = REGISTERED_STRATEGIES[strategy_version]()
    decisions: list[dict[str, str]] = []
    for index in range(len(candles)):
        if index + 1 < WARMUP_CANDLES:
            decisions.append({
                "decision": "AGUARDAR",
                "signal": Signal.AGUARDAR.value,
                "reason": "Strategy warm-up: insufficient closed-candle history",
            })
            continue
        # The pipeline sees only the current candle and its past; all candles
        # are historical closed bars, so confirmed=True is valid for replay.
        analysis = pipeline.evaluate(
            candles[: index + 1],
            confirmed=True,
            filters_ok=True,
            filters_required=True,
        )
        signal = analysis.signal
        decisions.append({
            "decision": "EXECUTAR" if signal in (Signal.COMPRA, Signal.VENDA) else "AGUARDAR",
            "signal": signal.value,
            "reason": analysis.reason,
        })

    from analysis.historical_trial_evaluator import evaluate_and_record_trial

    result = evaluate_and_record_trial(
        ledger=ledger,
        tenant_context=tenant_context,
        phase=phase,
        experiment_id=experiment_id,
        trial_id=trial_id,
        strategy_version=strategy_version,
        dataset_id=dataset_id,
        candles_payload=candles_payload,
        decisions_payload=decisions,
        take_profit_distance=take_profit_distance,
        stop_loss_distance=stop_loss_distance,
    )
    result["data_provenance"]["decision_stream"] = "GENERATED_BY_REGISTERED_IN_REPOSITORY_STRATEGY"
    result["data_provenance"]["strategy_id"] = strategy_version
    result["data_provenance"]["warmup_candles"] = WARMUP_CANDLES
    result["research_limitations"] = [
        "Caller-supplied candle payload is not independently verified against a provider snapshot.",
        "The current historical backtest is gross of spread, commission and slippage.",
        "This replay is diagnostic only; it does not run the robustness promotion gate.",
    ]
    result["promotion_allowed"] = False
    result["execution_authorized"] = False
    result["orders_submitted"] = False
    return result
