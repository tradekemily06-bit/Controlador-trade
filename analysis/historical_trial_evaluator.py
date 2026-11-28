"""Run a chronological, read-only historical trial and persist its evidence.

The decision stream is supplied by the caller and is therefore explicitly
identified as externally produced; this module never invents strategy signals.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from core.decision_engine import DecisionResult, FinalDecision
from core.historical_validation import HistoricalValidationEngine
from data.models import Candle
from core.models import Signal


def _utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _candle_fingerprint(candles: Sequence[Candle]) -> str:
    payload = [{
        "timestamp": candle.timestamp.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    } for candle in candles]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_and_record_trial(
    *,
    ledger: Any,
    tenant_context: Any,
    phase: str,
    experiment_id: str,
    trial_id: str,
    strategy_version: str,
    dataset_id: str,
    candles_payload: Sequence[Mapping[str, Any]],
    decisions_payload: Sequence[Mapping[str, Any]],
    take_profit_distance: float,
    stop_loss_distance: float,
) -> dict[str, Any]:
    """Evaluate caller-produced decisions against immutable OHLCV data and record metrics."""
    if phase not in {"SELECTION", "HOLDOUT"}:
        raise ValueError("phase must be SELECTION or HOLDOUT")
    if not isinstance(candles_payload, (list, tuple)) or not 2 <= len(candles_payload) <= 50000:
        raise ValueError("candles must contain between 2 and 50000 records")
    if not isinstance(decisions_payload, (list, tuple)) or len(decisions_payload) != len(candles_payload):
        raise ValueError("decisions must contain exactly one record per candle")

    candles: list[Candle] = []
    decisions: list[DecisionResult] = []
    for index, row in enumerate(candles_payload):
        if not isinstance(row, Mapping):
            raise ValueError(f"candle {index} must be an object")
        timestamp = _utc_timestamp(row.get("timestamp"), f"candles[{index}].timestamp")
        candles.append(Candle(
            timestamp=timestamp,
            open=row.get("open"), high=row.get("high"), low=row.get("low"),
            close=row.get("close"), volume=row.get("volume"),
        ))

    for index, row in enumerate(decisions_payload):
        if not isinstance(row, Mapping):
            raise ValueError(f"decision {index} must be an object")
        try:
            signal = Signal(row.get("signal"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"decisions[{index}].signal is invalid") from exc
        decision = row.get("decision")
        if decision not in {FinalDecision.EXECUTAR, FinalDecision.BLOQUEAR, FinalDecision.AGUARDAR}:
            raise ValueError(f"decisions[{index}].decision is invalid")
        reason = row.get("reason", "Externally supplied historical decision")
        if not isinstance(reason, str) or len(reason) > 500:
            raise ValueError(f"decisions[{index}].reason must be text up to 500 characters")
        decisions.append(DecisionResult(decision=decision, signal=signal, reason=reason))

    def decision_function(history: Sequence[Candle]) -> DecisionResult:
        return decisions[len(history) - 1]

    result = HistoricalValidationEngine().run(
        candles=candles,
        decision_function=decision_function,
        take_profit_distance=take_profit_distance,
        stop_loss_distance=stop_loss_distance,
    )
    start = candles[0].timestamp
    end = candles[-1].timestamp
    evaluated_at = datetime.now(timezone.utc)
    backtest = result.backtest
    profit_factor = backtest.profit_factor
    metrics = {
        "total_trades": backtest.total_trades,
        "wins": backtest.wins,
        "losses": backtest.losses,
        "ambiguous": backtest.ambiguous,
        "pending": backtest.pending,
        "win_rate_percent": backtest.win_rate,
        "profit_factor": profit_factor if math.isfinite(profit_factor) else "UNDEFINED_NO_LOSSES",
        "total_profit": backtest.total_profit,
        "max_drawdown": backtest.max_drawdown,
        "max_consecutive_losses": backtest.max_consecutive_losses,
        "executed_decisions": result.executed,
        "blocked_decisions": result.blocked,
        "waiting_decisions": result.waiting,
    }
    record = {
        "experiment_id": experiment_id,
        "trial_id": trial_id,
        "strategy_version": strategy_version,
        "dataset_id": dataset_id,
        "dataset_fingerprint": _candle_fingerprint(candles),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "evaluated_at": evaluated_at.isoformat(),
        "metrics": metrics,
    }
    if phase == "SELECTION":
        stored = ledger.record_selection_trial(tenant_context, **record)
    else:
        stored = ledger.record_holdout_evaluation(tenant_context, **record)
    return {
        "phase": phase,
        "strategy_trial": stored,
        "metrics": metrics,
        "data_provenance": {
            "dataset_fingerprint": record["dataset_fingerprint"],
            "candle_count": len(candles),
            "decision_stream": "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED",
            "chronological_replay": True,
        },
        "execution_authorized": False,
        "orders_submitted": False,
    }
