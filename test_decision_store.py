from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore


def make_record(decision_id: str = "d-1", outcome: str | None = None) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-09-11T12:00:00+00:00",
        symbol="EURUSD",
        timeframe="M5",
        signal="COMPRA",
        score=91.0,
        confirmed=True,
        reason="Confirmação de teste.",
        execution_allowed=False,
        outcome=outcome,
    )


def test_decision_store_persists_and_loads(tmp_path):
    database = tmp_path / "decisions.sqlite3"
    first = DecisionStore(str(database))
    first.save(make_record())

    second = DecisionStore(str(database))
    loaded = second.load()

    assert len(loaded) == 1
    assert loaded[0] == make_record()


def test_decision_store_updates_outcome_without_duplicate(tmp_path):
    database = tmp_path / "decisions.sqlite3"
    store = DecisionStore(str(database))
    store.save(make_record())
    store.save(make_record(outcome="WIN"))

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].outcome == "WIN"


def test_decision_store_is_optional_and_in_memory_compatible(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_DECISION_DB", raising=False)
    store = DecisionStore()
    assert store.database_path is None
    assert store.load() == []


def test_decision_store_failure_is_fail_soft(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("blocked", encoding="utf-8")
    store = DecisionStore(str(blocked / "decisions.sqlite3"))

    assert store.database_path is None
    store.save(make_record())
    assert store.load() == []
