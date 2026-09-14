from integration.ecosystem_service import EcosystemService
from analysis.decision_store import DecisionStore


class FailingOutcomeStore(DecisionStore):
    def __init__(self):
        super().__init__(database_path=None)

    def save(self, record):
        raise RuntimeError("durable write failed")


def test_outcome_does_not_mutate_memory_when_persistence_fails():
    service = EcosystemService(decision_store=FailingOutcomeStore())
    record = service.analyze(
        {"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"}
    )

    try:
        service.record_outcome(record.decision_id, "WIN")
    except RuntimeError as exc:
        assert "durable write failed" in str(exc)
    else:
        raise AssertionError("persistence failure should be surfaced")

    stored = service.memory_view()[0]
    assert stored["decision_id"] == record.decision_id
    assert stored["outcome"] is None
