import sqlite3

from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore


def _record():
    return DecisionRecord(
        decision_id="decision-1",
        created_at="2026-09-30T12:00:00+00:00",
        symbol="EURUSD",
        timeframe="5m",
        signal="COMPRA",
        score=85.0,
        confirmed=True,
        reason="teste",
    )


def test_decision_memory_survives_restart(tmp_path):
    database = tmp_path / "decision-memory.sqlite"
    store = DecisionStore(database)
    store.save(_record())

    restored = DecisionStore(database).load()

    assert len(restored) == 1
    assert restored[0].decision_id == "decision-1"
    assert restored[0].outcome_source == "MANUAL_STUDY"


def test_legacy_decision_schema_migrates_outcome_source(tmp_path):
    database = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT,
                timeframe TEXT, signal TEXT NOT NULL, score REAL NOT NULL,
                confirmed INTEGER NOT NULL, reason TEXT NOT NULL,
                execution_allowed INTEGER NOT NULL, outcome TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "2026-09-30T12:00:00+00:00", "EURUSD", "5m", "COMPRA", 80.0, 1, "legacy", 0, None),
        )

    restored = DecisionStore(database).load()

    assert len(restored) == 1
    assert restored[0].outcome_source == "MANUAL_STUDY"
