from datetime import datetime, timedelta, timezone

import pytest

from analysis.historical_trial_evaluator import evaluate_and_record_trial
from analysis.tenant_strategy_trial_ledger import TenantStrategyTrialLedger
from security.tenant_context import TenantContext


OWNER = TenantContext("tenant-a", "user-a")


def payload(start):
    candles = []
    for index in range(4):
        price = 100 + index
        candles.append({
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": price, "high": price + 1, "low": price - 1,
            "close": price, "volume": 10,
        })
    decisions = [
        {"decision": "EXECUTAR", "signal": "COMPRA"},
        {"decision": "AGUARDAR", "signal": "AGUARDAR"},
        {"decision": "AGUARDAR", "signal": "AGUARDAR"},
        {"decision": "AGUARDAR", "signal": "AGUARDAR"},
    ]
    return candles, decisions


def run(ledger, *, phase="SELECTION", trial_id="trial-1", start=None):
    candles, decisions = payload(start or datetime(2026, 1, 1, tzinfo=timezone.utc))
    return evaluate_and_record_trial(
        ledger=ledger, tenant_context=OWNER, phase=phase,
        experiment_id="experiment-1", trial_id=trial_id,
        strategy_version="strategy-v1", dataset_id=trial_id,
        candles_payload=candles, decisions_payload=decisions,
        take_profit_distance=0.5, stop_loss_distance=0.5,
    )


def test_runs_chronological_engine_and_records_real_metrics(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    result = run(ledger)

    assert result["data_provenance"]["chronological_replay"] is True
    assert result["data_provenance"]["decision_stream"] == "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED"
    assert result["metrics"]["total_trades"] == 1
    assert result["metrics"]["wins"] == 1
    assert result["strategy_trial"]["status"] == "RECORDED"
    assert len(ledger.list_experiment(OWNER, "experiment-1")) == 1


def test_holdout_uses_a_distinct_fingerprint_and_later_window(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    selection = run(ledger)
    later = datetime(2026, 2, 1, tzinfo=timezone.utc)
    holdout = run(ledger, phase="HOLDOUT", trial_id="holdout-1", start=later)

    assert selection["data_provenance"]["dataset_fingerprint"] != holdout["data_provenance"]["dataset_fingerprint"]
    assert holdout["strategy_trial"]["phase"] == "HOLDOUT"


def test_rejects_malformed_or_mismatched_decision_stream(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    candles, decisions = payload(datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="exactly one"):
        evaluate_and_record_trial(
            ledger=ledger, tenant_context=OWNER, phase="SELECTION",
            experiment_id="experiment-1", trial_id="bad", strategy_version="v1",
            dataset_id="d", candles_payload=candles, decisions_payload=decisions[:-1],
            take_profit_distance=1, stop_loss_distance=1,
        )
