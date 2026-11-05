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
    db.execute("ALTER TABLE fiscal_reserve_pending_foreign DROP COLUMN record_kind")
    db.execute("ALTER TABLE fiscal_reserve_pending_foreign DROP COLUMN original_result")
    for column in ("tax_residency_at_event", "income_nature", "event_type", "fx_conversion_method"):
        db.execute(f"ALTER TABLE fiscal_reserve_pending_foreign DROP COLUMN {column}")
    db.commit()
    db.close()

    migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    columns = {row[1] for row in db.execute("PRAGMA table_info(fiscal_reserve_pending_foreign)")}
    assert {"original_result", "record_kind", "tax_residency_at_event", "income_nature", "event_type", "fx_conversion_method"} <= columns
    assert db.execute(
        "SELECT original_result,record_kind,tax_residency_at_event,income_nature,event_type,fx_conversion_method "
        "FROM fiscal_reserve_pending_foreign WHERE pending_id='p1'"
    ).fetchone() == (None, "ASSET_AMOUNT", "NOT_INFORMED", "NOT_INFORMED", "NOT_INFORMED", "NOT_INFORMED")
    db.close()

def test_rebuild_preserves_signed_results_in_partially_migrated_owner_schema(tmp_path, monkeypatch):
    path = str(tmp_path / "partially-owned.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    owner = migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO fiscal_reserve_pending_foreign "
        "(pending_id,owner_id,reference,original_amount,original_result,record_kind,"
        "original_currency,instrument,jurisdiction,occurred_on,tax_residency_at_event,"
        "income_nature,event_type,fx_conversion_method,notes,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("p1", owner, "signed-result", 12.5, -12.5, "REALIZED_RESULT",
         "EUR", "FUTURES", "PENDING_REVIEW", "2026-11-03", "BRAZIL",
         "CAPITAL_GAIN", "DISPOSAL", "PTAX_SELL", "",
         "PENDING_CLASSIFICATION", "now"),
    )
    # Simulate a partially migrated database: one fiscal table still has its
    # legacy shape, forcing the atomic rebuild path for all four tables.
    db.execute("DROP TABLE fiscal_reserve_settings")
    db.execute(
        "CREATE TABLE fiscal_reserve_settings(category TEXT PRIMARY KEY, rate REAL NOT NULL)"
    )
    db.execute("INSERT INTO fiscal_reserve_settings VALUES('BR_DAY_TRADE',20)")
    db.commit()
    db.close()

    assert migrate_fiscal_schema(path) == owner
    db = sqlite3.connect(path)
    assert db.execute(
        "SELECT original_amount,original_result,record_kind,tax_residency_at_event,income_nature,event_type,fx_conversion_method FROM "
        "fiscal_reserve_pending_foreign WHERE pending_id='p1'"
    ).fetchone() == (12.5, -12.5, "REALIZED_RESULT", "BRAZIL", "CAPITAL_GAIN", "DISPOSAL", "PTAX_SELL")
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()


def test_existing_owner_schema_repairs_missing_default_rate_without_overwriting_custom_rate(tmp_path, monkeypatch):
    path = str(tmp_path / "owned-missing-rate.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.com")
    owner = migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    db.execute(
        "DELETE FROM fiscal_reserve_settings WHERE owner_id=? AND category='BR_DAY_TRADE'",
        (owner,),
    )
    db.commit()
    db.close()

    assert migrate_fiscal_schema(path) == owner
    db = sqlite3.connect(path)
    assert db.execute(
        "SELECT rate FROM fiscal_reserve_settings WHERE owner_id=? AND category='BR_DAY_TRADE'",
        (owner,),
    ).fetchone() == (20.0,)
    db.execute(
        "UPDATE fiscal_reserve_settings SET rate=17.5 WHERE owner_id=? AND category='BR_DAY_TRADE'",
        (owner,),
    )
    db.commit()
    db.close()

    migrate_fiscal_schema(path)
    db = sqlite3.connect(path)
    assert db.execute(
        "SELECT rate FROM fiscal_reserve_settings WHERE owner_id=? AND category='BR_DAY_TRADE'",
        (owner,),
    ).fetchone() == (17.5,)
    db.close()

def test_migration_refuses_a_different_owner_for_domestic_pending_queue(tmp_path, monkeypatch):
    from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
    from finance.fiscal_identity import configured_fiscal_owner_id

    path = str(tmp_path / "domestic-owned.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    owner = configured_fiscal_owner_id()
    queue = FiscalDomesticPendingQueue(path)
    queue.add(owner, {
        "reference": "BR-OWNER-A",
        "instrument": "ETF",
        "occurred_on": "2026-11-03",
    })
    migrate_fiscal_schema(path)

    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-b")
    with pytest.raises(RuntimeError, match="proprietário da fila brasileira"):
        migrate_fiscal_schema(path)
    assert queue.list_pending(owner)["total"] == 1


def test_partial_rebuild_refuses_to_reassign_existing_owner(tmp_path, monkeypatch):
    path = str(tmp_path / "partial-owner-mismatch.sqlite3")
    _legacy_db(path)
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    owner_a = migrate_fiscal_schema(path)

    # Force the rebuild path while leaving other tables with owner-a records.
    db = sqlite3.connect(path)
    db.execute("DROP TABLE fiscal_reserve_settings")
    db.execute(
        "CREATE TABLE fiscal_reserve_settings(category TEXT PRIMARY KEY, rate REAL NOT NULL)"
    )
    db.execute("INSERT INTO fiscal_reserve_settings VALUES('BR_DAY_TRADE', 20)")
    db.commit()
    db.close()

    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-b")
    with pytest.raises(RuntimeError, match="proprietário já gravado"):
        migrate_fiscal_schema(path)

    db = sqlite3.connect(path)
    assert db.execute(
        "SELECT DISTINCT owner_id FROM fiscal_reserve_entries"
    ).fetchall() == [(owner_a,)]
    assert db.execute(
        "SELECT COUNT(*) FROM fiscal_reserve_entries"
    ).fetchone()[0] == 1
    # The failed migration must leave the legacy settings table untouched.
    settings_columns = {
        row[1] for row in db.execute("PRAGMA table_info(fiscal_reserve_settings)")
    }
    assert "owner_id" not in settings_columns
    assert db.execute(
        "SELECT rate FROM fiscal_reserve_settings WHERE category='BR_DAY_TRADE'"
    ).fetchone() == (20.0,)
    db.close()



def test_owner_scoped_fast_path_rejects_orphaned_foreign_reviews(tmp_path, monkeypatch):
    path = str(tmp_path / "owner-scoped-orphan.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    owner = migrate_fiscal_schema(path)

    # Simulate corruption introduced by an external writer that did not enable
    # SQLite foreign-key enforcement on its connection.
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO fiscal_pending_reviews "
            "(review_id,owner_id,pending_id,candidate_classification,confirmed_jurisdiction,"
            "reviewer_name,reviewer_role,professional_registration,evidence_reference,"
            "reviewed_on,review_notes,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("orphan-review", owner, "missing-pending", "ETF", "US", "Reviewer",
             "contador", "CRC-X", "DOC-X", "2026-11-04", "", "now"),
        )

    with pytest.raises(RuntimeError, match="integridade referencial inválida"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM fiscal_pending_reviews WHERE review_id='orphan-review'"
        ).fetchone()[0] == 1

def test_application_migrates_owner_schema_before_fiscal_repositories_are_created():
    import ast
    from pathlib import Path

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    migration_index = None
    repository_indexes = []

    for index, statement in enumerate(tree.body):
        value = None
        if isinstance(statement, ast.Assign):
            value = statement.value
        elif isinstance(statement, ast.Expr):
            value = statement.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        if value.func.id == "migrate_fiscal_schema":
            migration_index = index
        elif value.func.id in {"FiscalReserve", "FiscalPendingQueue", "FiscalDomesticPendingQueue"}:
            repository_indexes.append(index)

    assert migration_index is not None, "app.py must apply the owner-scoped fiscal migration"
    assert repository_indexes, "app.py must initialize fiscal repositories"
    assert all(migration_index < index for index in repository_indexes), (
        "owner-scoped migration must run before any fiscal repository initialization"
    )
