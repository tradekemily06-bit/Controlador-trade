from datetime import datetime, timedelta, timezone

from analysis.tenant_strategy_trial_ledger import TenantStrategyTrialLedger
from integration.standalone_application_factory import build_standalone_application
from security.tenant_context import TenantContext


class StubEcosystemService:
    def learning_summary(self):
        return {"status": "READY"}


OWNER = TenantContext("tenant-a", "user-a")


def trial_context():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
    return {
        "operation": "evaluate_historical_trial",
        "phase": "SELECTION",
        "experiment_id": "experiment-1",
        "trial_id": "trial-1",
        "strategy_version": "strategy-v1",
        "dataset_id": "dataset-1",
        "candles": candles,
        "decisions": decisions,
        "take_profit_distance": 0.5,
        "stop_loss_distance": 0.5,
        # Must never override the tenant identity injected by the host.
        "tenant_id": "attacker-tenant",
        "subject_id": "attacker-user",
    }


def test_study_area_runs_and_persists_historical_trial_for_trusted_tenant(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    app = build_standalone_application(
        ecosystem_service=StubEcosystemService(),
        strategy_trial_ledger=ledger,
        strategy_trial_context=OWNER,
    )

    response = app.handle(area="study", task="evaluate historical strategy", context=trial_context())

    assert response["status"] == "CONNECTED"
    assert response["result"]["strategy_trial"]["status"] == "RECORDED"
    assert response["result"]["execution_authorized"] is False
    assert response["result"]["orders_submitted"] is False
    assert len(ledger.list_experiment(OWNER, "experiment-1")) == 1
    assert ledger.list_experiment(
        TenantContext("attacker-tenant", "attacker-user"), "experiment-1"
    ) == []


def test_study_area_fails_closed_without_host_injected_tenant_context(tmp_path):
    ledger = TenantStrategyTrialLedger(tmp_path / "trials.sqlite3")
    app = build_standalone_application(
        ecosystem_service=StubEcosystemService(),
        strategy_trial_ledger=ledger,
        strategy_trial_context=None,
    )

    response = app.handle(area="study", task="evaluate historical strategy", context=trial_context())

    assert response["status"] == "CONNECTED"
    assert response["result"]["status"] == "TRUSTED_TENANT_CONTEXT_NOT_CONFIGURED"
    assert ledger.list_experiment(OWNER, "experiment-1") == []
