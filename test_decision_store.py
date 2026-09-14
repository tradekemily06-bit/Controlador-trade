from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore
import pytest


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


def test_configured_decision_store_fails_closed_when_database_path_is_unavailable(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("blocked", encoding="utf-8")
    with pytest.raises(RuntimeError, match="decision storage could not be initialized"):
        DecisionStore(str(blocked / "decisions.sqlite3"))


def test_decision_store_migrates_legacy_database_with_owner_columns(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    legacy = DecisionStore.__new__(DecisionStore)
    legacy.database_path = str(database)
    legacy._lock = __import__("threading").Lock()
    with legacy._lock, legacy._connect() as connection:
        connection.execute("CREATE TABLE decisions (decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT, timeframe TEXT, signal TEXT NOT NULL, score REAL NOT NULL, confirmed INTEGER NOT NULL, reason TEXT NOT NULL, execution_allowed INTEGER NOT NULL, outcome TEXT)")
        connection.execute("INSERT INTO decisions VALUES ('legacy', '2026-09-11T12:00:00+00:00', 'EURUSD', 'M5', 'COMPRA', 90, 1, 'legacy', 0, NULL)")

    migrated = DecisionStore(str(database))
    loaded = migrated.load()
    assert loaded[0].decision_id == "legacy"
    assert loaded[0].subject_id is None
    assert loaded[0].tenant_id is None
