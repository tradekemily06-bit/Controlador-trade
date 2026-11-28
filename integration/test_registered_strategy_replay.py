from datetime import datetime, timedelta, timezone

import pytest

from analysis.tenant_strategy_trial_ledger import TenantStrategyTrialLedger
from integration.standalone_application_factory import build_standalone_application
from security.tenant_context import TenantContext


class StubEcosystemService:
    def learning_summary(self):
        return {"status": "READY"}


OWNER = TenantContext("tenant-a", "user-a")


def rising_candles(count=36):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        price = 100.0 + index * 0.2
        rows.append({
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": price - 0.05,
            "high": price + 0.15,
            "low": price - 0.15,
            "close": price + 0.05,
            "volume": 100 + index,
        })
    return rows


def test_study_runs_registered_strategy_and_records_generated_decisions(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    app = build_standalone_application(
        ecosystem_service=StubEcosystemService(),
        strategy_trial_ledger=ledger,
        strategy_trial_context=OWNER,
    )
    response = app.handle(
        area="study",
        task="evaluate registered strategy",
        context={
            "operation": "evaluate_registered_strategy_trial",
            "phase": "SELECTION",
            "experiment_id": "registered-exp",
            "trial_id": "registered-trial-1",
            "strategy_version": "technical-pipeline-v1",
            "dataset_id": "caller-candle-window",
            "candles": rising_candles(),
            "take_profit_distance": 0.5,
            "stop_loss_distance": 0.5,
            "tenant_id": "attacker",
            "subject_id": "attacker",
        },
    )

    assert response["status"] == "CONNECTED"
    result = response["result"]
    assert result["data_provenance"]["decision_stream"] == "GENERATED_BY_REGISTERED_IN_REPOSITORY_STRATEGY"
    assert result["data_provenance"]["strategy_id"] == "technical-pipeline-v1"
    assert result["data_provenance"]["warmup_candles"] == 30
    assert result["promotion_allowed"] is False
    assert result["execution_authorized"] is False
    assert result["orders_submitted"] is False
    assert len(ledger.list_experiment(OWNER, "registered-exp")) == 1


def test_study_rejects_unregistered_strategy_version(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    app = build_standalone_application(
        ecosystem_service=StubEcosystemService(),
        strategy_trial_ledger=ledger,
        strategy_trial_context=OWNER,
    )
    with pytest.raises(ValueError, match="not registered"):
        app.handle(
            area="study",
            task="evaluate unregistered strategy",
            context={
                "operation": "evaluate_registered_strategy_trial",
                "phase": "SELECTION",
                "experiment_id": "unknown-exp",
                "trial_id": "unknown-trial",
                "strategy_version": "caller-invented-v99",
                "dataset_id": "dataset",
                "candles": rising_candles(),
                "take_profit_distance": 0.5,
                "stop_loss_distance": 0.5,
            },
        )
    assert ledger.list_experiment(OWNER, "unknown-exp") == []
