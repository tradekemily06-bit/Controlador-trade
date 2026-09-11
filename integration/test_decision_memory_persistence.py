from analysis.decision_store import DecisionStore
from integration.ecosystem_service import EcosystemService


def test_ecosystem_service_restores_decisions_and_outcomes(tmp_path):
    database = tmp_path / "decisions.sqlite3"

    first = EcosystemService(decision_store=DecisionStore(str(database)))
    record = first.analyze({
        "score": 88,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })
    first.record_outcome(record.decision_id, "WIN")

    second = EcosystemService(decision_store=DecisionStore(str(database)))
    restored = second.memory_view()

    assert len(restored) == 1
    assert restored[0]["decision_id"] == record.decision_id
    assert restored[0]["outcome"] == "WIN"
    assert second.statistics()["total"] == 1
