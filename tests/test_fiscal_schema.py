import os
import sqlite3

import pytest

from finance.fiscal_schema import migrate_fiscal_schema


def _legacy_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE fiscal_reserve_settings(category TEXT PRIMARY KEY, rate REAL NOT NULL);
        INSERT INTO fiscal_reserve_settings VALUES ('BR_DAY_TRADE', 20);
        CREATE TABLE fiscal_reserve_entries(
            entry_id TEXT PRIMARY KEY, category TEXT NOT NULL, entry_type TEXT NOT NULL,
            realized_result_brl REAL NOT NULL, reserve_rate REAL NOT NULL,
            reserve_amount_brl REAL NOT NULL, reference TEXT NOT NULL,
            occurred_on TEXT NOT NULL, created_at TEXT NOT NULL, notes TEXT NOT NULL
        );
        INSERT INTO fiscal_reserve_entries VALUES
        ('e1','BR_DAY_TRADE','REALIZED_RESULT',100,20,20,'ref1','2026-11-01','now','');
        CREATE UNIQUE INDEX ux_fiscal_reserve_category_reference
        ON fiscal_reserve_entries(category, reference);
        CREATE TABLE fiscal_reserve_pending_foreign(
            pending_id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            original_amount REAL NOT NULL, original_currency TEXT NOT NULL,
            instrument TEXT NOT NULL, jurisdiction TEXT NOT NULL, occurred_on TEXT NOT NULL,
            fx_rate REAL, fx_date TEXT, fx_source TEXT, notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO fiscal_reserve_pending_foreign VALUES
        ('p1','pending-ref',10,'USD','ETF','US','2026-11-01',NULL,NULL,NULL,'',
         'PENDING_CLASSIFICATION','now');
        CREATE TABLE fiscal_pending_reviews(
            review_id TEXT PRIMARY KEY, pending_id TEXT NOT NULL,
            candidate_classification TEXT NOT NULL, confirmed_jurisdiction TEXT NOT NULL,
            reviewer_name TEXT NOT NULL, reviewer_role TEXT NOT NULL,
            professional_registration TEXT NOT NULL, evidence_reference TEXT NOT NULL,
            reviewed_on TEXT NOT NULL, review_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(pending_id) REFERENCES fiscal_reserve_pending_foreign(pending_id)
        );
        INSERT INTO fiscal_pending_reviews VALUES
        ('r1','p1','ETF','US','Reviewer','contador','CRC-X','DOC-X','2026-11-02','','now');
    """)
    db.commit()
    db.close()


def test_migration_assigns_legacy_rows_and_adds_composite_review_fk(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.sqlite3")
    _legacy_db(path)
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    owner = migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT owner_id FROM fiscal_reserve_entries WHERE entry_id='e1'").fetchone()[0] == owner
    assert db.execute("SELECT owner_id FROM fiscal_reserve_pending_foreign WHERE pending_id='p1'").fetchone()[0] == owner
    assert db.execute("SELECT owner_id FROM fiscal_pending_reviews WHERE review_id='r1'").fetchone()[0] == owner
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("SELECT rate FROM fiscal_reserve_settings WHERE owner_id=? AND category='BR_DAY_TRADE'", (owner,)).fetchone()[0] == 20
    db.close()


def test_migration_is_idempotent(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.sqlite3")
    _legacy_db(path)
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    first = migrate_fiscal_schema(path)
    second = migrate_fiscal_schema(path)
    assert first == second
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM fiscal_reserve_entries").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM fiscal_pending_reviews").fetchone()[0] == 1
    db.close()


def test_migration_without_configured_identity_changes_nothing(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.sqlite3")
    _legacy_db(path)
    monkeypatch.delenv("CONTROLADOR_SINGLE_USER_IDENTITY", raising=False)
    before = sqlite3.connect(path).execute(
        "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    with pytest.raises(RuntimeError):
        migrate_fiscal_schema(path)
    after = sqlite3.connect(path).execute(
        "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    assert before == after


def test_migration_refuses_to_reassign_an_existing_owner(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.sqlite3")
    _legacy_db(path)
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "first-owner")
    first_owner = migrate_fiscal_schema(path)
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "different-owner")
    with pytest.raises(RuntimeError, match="não corresponde ao proprietário"):
        migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT DISTINCT owner_id FROM fiscal_reserve_entries").fetchall() == [(first_owner,)]
    db.close()


def test_migration_adds_signed_result_fields_to_existing_owner_schema(tmp_path, monkeypatch):
    path = str(tmp_path / "owned.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    owner = migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO fiscal_reserve_pending_foreign "
        "(pending_id,owner_id,reference,original_amount,original_currency,instrument,jurisdiction,"
        "occurred_on,notes,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("p1", owner, "legacy", 10, "USD", "ETF", "US",
         "2026-11-03", "", "PENDING_CLASSIFICATION", "now"),
    )
    db.commit()
    db.close()

    migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    columns = {row[1] for row in db.execute("PRAGMA table_info(fiscal_reserve_pending_foreign)")}
    assert {"original_result", "record_kind"} <= columns
    assert db.execute(
        "SELECT original_result,record_kind FROM fiscal_reserve_pending_foreign WHERE pending_id='p1'"
    ).fetchone() == (None, "ASSET_AMOUNT")
    db.close()
