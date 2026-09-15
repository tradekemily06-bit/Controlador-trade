from __future__ import annotations

from analysis.decision_record import DecisionRecord
from storage.production_decision_store import ProductionDecisionStore
from storage.sqlite_production_store import SQLiteProductionStore


def test_sqlite_provider_persists_and_isolates_decisions(tmp_path) -> None:
    provider = SQLiteProductionStore(tmp_path / "production.sqlite3")
    store = ProductionDecisionStore(provider)
    record = DecisionRecord(
        decision_id="decision-1",
        created_at="2026-09-14T00:00:00+00:00",
        symbol="EURUSD",
        timeframe="5m",
        signal="VENDA",
        score=88.0,
        confirmed=True,
        reason="validated",
    )

    store.save(record, tenant_id="tenant-a", subject_id="user-a")
    reopened = ProductionDecisionStore(SQLiteProductionStore(tmp_path / "production.sqlite3"))

    loaded = reopened.load("decision-1", tenant_id="tenant-a", subject_id="user-a")
    assert loaded is not None
    assert loaded.signal == "VENDA"
    assert reopened.list(tenant_id="tenant-b", subject_id="user-a") == []
