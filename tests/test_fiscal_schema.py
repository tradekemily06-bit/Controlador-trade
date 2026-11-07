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
    process_lock_acquire_index = None
    runtime_construction_index = None
    repository_indexes = []

    for index, statement in enumerate(tree.body):
        value = None
        if isinstance(statement, ast.Assign):
            value = statement.value
        elif isinstance(statement, ast.Expr):
            value = statement.value
        if not isinstance(value, ast.Call):
            continue
        if isinstance(value.func, ast.Name):
            if value.func.id == "migrate_fiscal_schema":
                migration_index = index
            elif value.func.id in {"FiscalReserve", "FiscalPendingQueue", "FiscalDomesticPendingQueue"}:
                repository_indexes.append(index)
            elif value.func.id == "build_demo_execution_port":
                runtime_construction_index = index
        elif (
            isinstance(value.func, ast.Attribute)
            and value.func.attr == "acquire"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "_RUNTIME_PROCESS_LOCK"
        ):
            process_lock_acquire_index = index

    assert process_lock_acquire_index is not None, "app.py must acquire the process lock during startup"
    assert runtime_construction_index is not None, "app.py must construct the operational runtime"
    assert migration_index is not None, "app.py must apply the owner-scoped fiscal migration"
    assert process_lock_acquire_index < runtime_construction_index, (
        "process exclusivity must be acquired before operational runtime construction"
    )
    assert process_lock_acquire_index < migration_index, (
        "process exclusivity must be acquired before fiscal schema migration"
    )
    assert repository_indexes, "app.py must initialize fiscal repositories"
    assert all(migration_index < index for index in repository_indexes), (
        "owner-scoped migration must run before any fiscal repository initialization"
    )



def test_schema_validator_rejects_partial_unique_index_as_full_owner_constraint():
    from finance.fiscal_schema import _has_unique_index

    db = sqlite3.connect(":memory:")
    try:
        db.execute(
            "CREATE TABLE fiscal_reserve_pending_foreign "
            "(owner_id TEXT NOT NULL, reference TEXT, status TEXT NOT NULL)"
        )
        db.execute(
            "CREATE UNIQUE INDEX ux_partial_owner_reference "
            "ON fiscal_reserve_pending_foreign(owner_id, reference) "
            "WHERE status = 'PENDING_CLASSIFICATION'"
        )

        assert _has_unique_index(
            db, "fiscal_reserve_pending_foreign", ("owner_id", "reference")
        ) is False
    finally:
        db.close()

def test_owner_fast_path_rebuilds_global_reference_uniqueness(tmp_path, monkeypatch):
    path = str(tmp_path / "wrong-owner-constraints.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    owner = migrate_fiscal_schema(path)

    # Simulate owner-tagged tables with global uniqueness and an incomplete FK.
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TABLE fiscal_pending_reviews")
        db.execute("DROP TABLE fiscal_reserve_pending_foreign")
        db.execute("""CREATE TABLE fiscal_reserve_pending_foreign (
            pending_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
            original_amount REAL NOT NULL, original_currency TEXT NOT NULL, instrument TEXT NOT NULL,
            jurisdiction TEXT NOT NULL, occurred_on TEXT NOT NULL, fx_rate REAL, fx_date TEXT,
            fx_source TEXT, notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
            original_result REAL, record_kind TEXT NOT NULL DEFAULT 'ASSET_AMOUNT',
            tax_residency_at_event TEXT NOT NULL DEFAULT 'NOT_INFORMED',
            income_nature TEXT NOT NULL DEFAULT 'NOT_INFORMED', event_type TEXT NOT NULL DEFAULT 'NOT_INFORMED',
            fx_conversion_method TEXT NOT NULL DEFAULT 'NOT_INFORMED', created_at TEXT NOT NULL
        )""")
        db.execute("""INSERT INTO fiscal_reserve_pending_foreign
            (pending_id,owner_id,reference,original_amount,original_currency,instrument,jurisdiction,occurred_on,notes,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("p1", owner, "kept-ref", 25, "USD", "ETF", "US", "2026-11-05", "", "PENDING_CLASSIFICATION", "now"))
        db.execute("""CREATE TABLE fiscal_pending_reviews (
            review_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pending_id TEXT NOT NULL,
            candidate_classification TEXT NOT NULL, confirmed_jurisdiction TEXT NOT NULL,
            reviewer_name TEXT NOT NULL, reviewer_role TEXT NOT NULL, professional_registration TEXT NOT NULL,
            evidence_reference TEXT NOT NULL, reviewed_on TEXT NOT NULL, review_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, FOREIGN KEY(pending_id) REFERENCES fiscal_reserve_pending_foreign(pending_id)
        )""")

    assert migrate_fiscal_schema(path) == owner
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT owner_id,reference FROM fiscal_reserve_pending_foreign WHERE pending_id='p1'"
        ).fetchone() == (owner, "kept-ref")
        unique_indexes = [
            row[1] for row in db.execute("PRAGMA index_list(fiscal_reserve_pending_foreign)") if row[2]
        ]
        indexed_columns = [
            tuple(row[2] for row in db.execute(f"PRAGMA index_info('{name}')"))
            for name in unique_indexes
        ]
        assert ("owner_id", "reference") in indexed_columns
        assert ("owner_id", "pending_id") in indexed_columns
        foreign_keys = list(db.execute("PRAGMA foreign_key_list(fiscal_pending_reviews)"))
        assert {(row[3], row[4]) for row in foreign_keys} == {
            ("owner_id", "owner_id"), ("pending_id", "pending_id")
        }
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO fiscal_reserve_pending_foreign
                (pending_id,owner_id,reference,original_amount,original_currency,instrument,jurisdiction,occurred_on,notes,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                ("p2", owner, "kept-ref", 10, "USD", "ETF", "US", "2026-11-05", "", "PENDING_CLASSIFICATION", "now"))


def test_migration_fails_closed_on_malformed_domestic_queue_constraints(tmp_path, monkeypatch):
    from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue

    path = str(tmp_path / "malformed-domestic.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    queue = FiscalDomesticPendingQueue(path)
    from finance.fiscal_identity import configured_fiscal_owner_id
    owner = configured_fiscal_owner_id()
    queue.add(owner, {
        "reference": "BR-KEEP-001",
        "instrument": "ETF",
        "occurred_on": "2026-11-05",
    })
    migrate_fiscal_schema(path)

    # Simulate a historical schema with globally unique references and a
    # review FK that checks pending_id but does not bind owner_id.
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TABLE fiscal_domestic_pending_reviews")
        db.execute("DROP TABLE fiscal_reserve_pending_domestic")
        db.execute("""CREATE TABLE fiscal_reserve_pending_domestic (
            pending_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
            category_candidate TEXT NOT NULL DEFAULT '', instrument TEXT NOT NULL,
            market_scope TEXT NOT NULL DEFAULT '', occurred_on TEXT NOT NULL,
            realized_result_brl REAL, notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        db.execute("""INSERT INTO fiscal_reserve_pending_domestic
            (pending_id,owner_id,reference,instrument,occurred_on,status,created_at)
            VALUES('br-p1',?,'BR-KEEP-001','ETF','2026-11-05','PENDING_CLASSIFICATION','now')""",
            (owner,))
        db.execute("""CREATE TABLE fiscal_domestic_pending_reviews (
            review_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pending_id TEXT NOT NULL,
            candidate_classification TEXT NOT NULL, confirmed_jurisdiction TEXT NOT NULL,
            reviewer_name TEXT NOT NULL, reviewer_role TEXT NOT NULL, professional_registration TEXT NOT NULL,
            evidence_reference TEXT NOT NULL, reviewed_on TEXT NOT NULL, review_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(pending_id) REFERENCES fiscal_reserve_pending_domestic(pending_id)
        )""")

    with pytest.raises(RuntimeError, match="Esquema da fila brasileira pendente inválido"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT owner_id,reference FROM fiscal_reserve_pending_domestic WHERE pending_id='br-p1'"
        ).fetchone()
        assert row == (owner, "BR-KEEP-001")


def test_migration_fails_closed_when_only_one_domestic_queue_table_exists(tmp_path, monkeypatch):
    from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue

    path = str(tmp_path / "partial-domestic.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "partial-domestic-owner")
    queue = FiscalDomesticPendingQueue(path)
    owner = migrate_fiscal_schema(path)
    queue.add(owner, {
        "reference": "BR-PARTIAL-KEEP",
        "instrument": "ETF",
        "occurred_on": "2026-11-05",
    })

    # Simulate an interrupted/manual schema change that removed only the
    # review table while leaving the owner-scoped pending records in place.
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE fiscal_domestic_pending_reviews")

    with pytest.raises(RuntimeError, match="Esquema da fila brasileira pendente incompleto"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT owner_id,reference FROM fiscal_reserve_pending_domestic "
            "WHERE reference='BR-PARTIAL-KEEP'"
        ).fetchone()
        assert row == (owner, "BR-PARTIAL-KEEP")



def test_owner_fast_path_rebuilds_cascading_review_fk_as_restrict(tmp_path, monkeypatch):
    path = str(tmp_path / "cascading-review-fk.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    owner = migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO fiscal_reserve_pending_foreign "
            "(pending_id,owner_id,reference,original_amount,original_currency,instrument,"
            "jurisdiction,occurred_on,notes,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("p1", owner, "ref-1", 10, "USD", "ETF", "PENDING_REVIEW",
             "2026-11-05", "", "PENDING_CLASSIFICATION", "now"),
        )
        db.execute("DROP TABLE fiscal_pending_reviews")
        db.execute("""CREATE TABLE fiscal_pending_reviews (
            review_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pending_id TEXT NOT NULL,
            candidate_classification TEXT NOT NULL, confirmed_jurisdiction TEXT NOT NULL,
            reviewer_name TEXT NOT NULL, reviewer_role TEXT NOT NULL,
            professional_registration TEXT NOT NULL, evidence_reference TEXT NOT NULL,
            reviewed_on TEXT NOT NULL, review_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id,pending_id)
                REFERENCES fiscal_reserve_pending_foreign(owner_id,pending_id)
                ON DELETE CASCADE
        )""")
        db.execute(
            "INSERT INTO fiscal_pending_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("r1", owner, "p1", "ETF", "PENDING_REVIEW", "Reviewer", "contador",
             "CRC-X", "DOC-X", "2026-11-05", "", "now"),
        )

    assert migrate_fiscal_schema(path) == owner
    with sqlite3.connect(path) as db:
        foreign_keys = list(db.execute("PRAGMA foreign_key_list(fiscal_pending_reviews)"))
        assert foreign_keys
        assert {row[6] for row in foreign_keys} == {"RESTRICT"}
        assert db.execute(
            "SELECT COUNT(*) FROM fiscal_pending_reviews WHERE review_id='r1'"
        ).fetchone()[0] == 1
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "DELETE FROM fiscal_reserve_pending_foreign WHERE pending_id='p1'"
            )



def test_migration_adds_and_preserves_structured_foreign_evidence_fields(tmp_path, monkeypatch):
    from finance.fiscal_pending_queue import FiscalPendingQueue

    path = str(tmp_path / "structured-evidence-migration.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "structured-owner")
    owner = migrate_fiscal_schema(path)
    queue = FiscalPendingQueue(path)
    pending = queue.add(owner, {
        "reference": "STRUCTURED-KEEP",
        "original_amount": 500,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-05",
        "institution": "Broker US",
        "custody_location": "Foreign custodian",
        "contract_type": "ETF spot",
        "acquisition_cost": 450,
        "transaction_fees": 3.25,
        "foreign_tax_paid": 8,
    })

    # Force the atomic rebuild path; the pending table must retain all evidence.
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE fiscal_reserve_settings")
        db.execute(
            "CREATE TABLE fiscal_reserve_settings(category TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        db.execute("INSERT INTO fiscal_reserve_settings VALUES('BR_DAY_TRADE', 20)")
    assert migrate_fiscal_schema(path) == owner

    stored = queue.list_pending(owner)["items"][0]
    assert stored["pending_id"] == pending["pending_id"]
    assert stored["institution"] == "Broker US"
    assert stored["custody_location"] == "Foreign custodian"
    assert stored["contract_type"] == "ETF spot"
    assert stored["acquisition_cost"] == 450
    assert stored["transaction_fees"] == 3.25
    assert stored["foreign_tax_paid"] == 8
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
