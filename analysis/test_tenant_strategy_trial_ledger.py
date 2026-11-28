from datetime import datetime, timezone

import pytest

from analysis.tenant_strategy_trial_ledger import TenantStrategyTrialLedger
from security.tenant_context import TenantContext


OWNER = TenantContext("tenant-a", "user-a")
OTHER = TenantContext("tenant-b", "user-b")
START = "2026-01-01T00:00:00Z"
END = "2026-02-01T00:00:00Z"
EVALUATED = "2026-02-02T00:00:00Z"
SELECTION_HASH = "a" * 64
HOLDOUT_HASH = "b" * 64


def selection(ledger, *, context=OWNER, trial_id="trial-1", fingerprint=SELECTION_HASH, metrics=None):
    return ledger.record_selection_trial(
        context,
        experiment_id="experiment-1",
        trial_id=trial_id,
        strategy_version="strategy-v1",
        dataset_id="selection-dataset",
        dataset_fingerprint=fingerprint,
        window_start=START,
        window_end=END,
        evaluated_at=EVALUATED,
        metrics=metrics or {"sharpe": 1.2, "trades": 42},
    )


def holdout(ledger, *, context=OWNER, trial_id="holdout-1", fingerprint=HOLDOUT_HASH):
    return ledger.record_holdout_evaluation(
        context,
        experiment_id="experiment-1",
        trial_id=trial_id,
        strategy_version="strategy-v1",
        dataset_id="untouched-holdout",
        dataset_fingerprint=fingerprint,
        window_start=START,
        window_end=END,
        evaluated_at="2026-02-03T00:00:00Z",
        metrics={"sharpe": 0.8, "trades": 12},
    )


def test_records_selection_trials_and_counts_them(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    first = selection(ledger)
    second = selection(ledger, trial_id="trial-2", metrics={"sharpe": 1.4})

    assert first["status"] == "RECORDED"
    assert second["selection_trial_count"] == 2
    assert len(ledger.list_experiment(OWNER, "experiment-1")) == 2


def test_holdout_requires_selection_and_a_distinct_dataset(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    with pytest.raises(ValueError, match="at least one"):
        holdout(ledger)

    selection(ledger)
    with pytest.raises(ValueError, match="must differ"):
        holdout(ledger, fingerprint=SELECTION_HASH)

    assert holdout(ledger)["status"] == "RECORDED"


def test_holdout_is_single_and_freezes_selection(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    selection(ledger)
    holdout(ledger)

    with pytest.raises(ValueError, match="only one"):
        holdout(ledger, trial_id="holdout-2")
    with pytest.raises(ValueError, match="frozen"):
        selection(ledger, trial_id="trial-after-holdout")


def test_identical_retry_is_idempotent_but_mutation_is_rejected(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    selection(ledger)
    assert selection(ledger)["status"] == "ALREADY_RECORDED"

    with pytest.raises(ValueError, match="different immutable"):
        selection(ledger, metrics={"sharpe": 99.0})


def test_records_are_isolated_by_tenant_and_subject(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    selection(ledger)
    assert ledger.list_experiment(OTHER, "experiment-1") == []


@pytest.mark.parametrize("fingerprint", ["not-a-hash", "A" * 64, "a" * 63])
def test_rejects_invalid_dataset_fingerprint(tmp_path, fingerprint):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    with pytest.raises(ValueError, match="SHA-256"):
        selection(ledger, fingerprint=fingerprint)


def test_rejects_naive_or_reversed_evaluation_windows(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    with pytest.raises(ValueError, match="timezone"):
        ledger.record_selection_trial(
            OWNER, experiment_id="e", trial_id="t", strategy_version="v1",
            dataset_id="d", dataset_fingerprint=SELECTION_HASH,
            window_start="2026-01-01T00:00:00", window_end=END,
            evaluated_at=EVALUATED, metrics={"sharpe": 1.0},
        )
    with pytest.raises(ValueError, match="ordered"):
        ledger.record_selection_trial(
            OWNER, experiment_id="e", trial_id="t", strategy_version="v1",
            dataset_id="d", dataset_fingerprint=SELECTION_HASH,
            window_start=END, window_end=START,
            evaluated_at=EVALUATED, metrics={"sharpe": 1.0},
        )


def test_rejects_non_finite_metrics(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    with pytest.raises(ValueError, match="NaN or infinity"):
        selection(ledger, metrics={"sharpe": float("nan")})
