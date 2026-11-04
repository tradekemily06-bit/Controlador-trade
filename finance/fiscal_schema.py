"""Atomic migration of all fiscal tables to the configured single owner."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from finance.fiscal_identity import configured_fiscal_owner_id


TABLES = (
    "fiscal_reserve_settings",
    "fiscal_reserve_entries",
    "fiscal_reserve_pending_foreign",
    "fiscal_pending_reviews",
)


def migrate_fiscal_schema(database_path: str) -> str:
    """Migrate all four fiscal tables in one transaction; abort if owner is unset.

    Existing rows are assigned to the one server-configured owner. The identity
    is never accepted as an argument and is never stored in clear text.
    """
    owner_id = configured_fiscal_owner_id()
    path = str(database_path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA busy_timeout = 20000")
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("BEGIN IMMEDIATE")
        existing = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if all(table in existing for table in TABLES):
            owner_columns = {
                table: {row["name"] for row in db.execute(f'PRAGMA table_info("{table}")')}
                for table in TABLES
            }
            if all("owner_id" in columns for columns in owner_columns.values()):
                pending_columns = owner_columns["fiscal_reserve_pending_foreign"]
                if "original_result" not in pending_columns:
                    db.execute("ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN original_result REAL")
                if "record_kind" not in pending_columns:
                    db.execute("ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN record_kind TEXT NOT NULL DEFAULT 'ASSET_AMOUNT'")
                stored_owners = set()
                for table in TABLES:
                    stored_owners.update(
                        row[0] for row in db.execute(
                            f'SELECT DISTINCT owner_id FROM "{table}" WHERE owner_id IS NOT NULL'
                        ).fetchall()
                    )
                if stored_owners and stored_owners != {owner_id}:
                    raise RuntimeError(
                        "A identidade fiscal configurada não corresponde ao proprietário já gravado; "
                        "migração automática entre proprietários foi bloqueada."
                    )
                db.commit()
                return owner_id

        # Capture the old layouts before replacing anything. A missing table is
        # treated as an empty table, which supports clean first-time installs.
        def rows(table: str):
            if table not in existing:
                return []
            return db.execute(f'SELECT * FROM "{table}"').fetchall()

        settings = rows("fiscal_reserve_settings")
        entries = rows("fiscal_reserve_entries")
        pending = rows("fiscal_reserve_pending_foreign")
        reviews = rows("fiscal_pending_reviews")

        for table in TABLES:
            db.execute(f'DROP TABLE IF EXISTS "{table}_new"')

        db.execute("""
            CREATE TABLE fiscal_reserve_settings_new (
                owner_id TEXT NOT NULL,
                category TEXT NOT NULL,
                rate REAL NOT NULL CHECK(rate >= 0 AND rate <= 100),
                PRIMARY KEY(owner_id, category)
            )
        """)
        db.execute("""
            CREATE TABLE fiscal_reserve_entries_new (
                entry_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                category TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                realized_result_brl REAL NOT NULL,
                reserve_rate REAL NOT NULL,
                reserve_amount_brl REAL NOT NULL,
                reference TEXT NOT NULL,
                occurred_on TEXT NOT NULL,
                created_at TEXT NOT NULL,
                notes TEXT NOT NULL,
                UNIQUE(owner_id, category, reference)
            )
        """)
        db.execute("""
            CREATE TABLE fiscal_reserve_pending_foreign_new (
                pending_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                reference TEXT NOT NULL,
                original_amount REAL NOT NULL,
                original_currency TEXT NOT NULL,
                instrument TEXT NOT NULL,
                jurisdiction TEXT NOT NULL,
                occurred_on TEXT NOT NULL,
                fx_rate REAL,
                fx_date TEXT,
                fx_source TEXT,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status = 'PENDING_CLASSIFICATION'),
                original_result REAL,
                record_kind TEXT NOT NULL DEFAULT 'ASSET_AMOUNT',
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, pending_id),
                UNIQUE(owner_id, reference)
            )
        """)
        db.execute("""
            CREATE TABLE fiscal_pending_reviews_new (
                review_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                pending_id TEXT NOT NULL,
                candidate_classification TEXT NOT NULL,
                confirmed_jurisdiction TEXT NOT NULL,
                reviewer_name TEXT NOT NULL,
                reviewer_role TEXT NOT NULL,
                professional_registration TEXT NOT NULL,
                evidence_reference TEXT NOT NULL,
                reviewed_on TEXT NOT NULL,
                review_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(owner_id, pending_id)
                    REFERENCES fiscal_reserve_pending_foreign_new(owner_id, pending_id)
                    ON DELETE RESTRICT
            )
        """)

        for row in settings:
            keys = set(row.keys())
            db.execute(
                "INSERT INTO fiscal_reserve_settings_new(owner_id,category,rate) VALUES(?,?,?)",
                (owner_id, row["category"], row["rate"]),
            )
        for row in entries:
            db.execute("""
                INSERT INTO fiscal_reserve_entries_new
                (entry_id,owner_id,category,entry_type,realized_result_brl,reserve_rate,
                 reserve_amount_brl,reference,occurred_on,created_at,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (row["entry_id"], owner_id, row["category"], row["entry_type"],
                  row["realized_result_brl"], row["reserve_rate"], row["reserve_amount_brl"],
                  row["reference"], row["occurred_on"], row["created_at"], row["notes"]))
        for row in pending:
            db.execute("""
                INSERT INTO fiscal_reserve_pending_foreign_new
                (pending_id,owner_id,reference,original_amount,original_currency,instrument,
                 jurisdiction,occurred_on,fx_rate,fx_date,fx_source,notes,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (row["pending_id"], owner_id, row["reference"], row["original_amount"],
                  row["original_currency"], row["instrument"], row["jurisdiction"],
                  row["occurred_on"], row["fx_rate"], row["fx_date"], row["fx_source"],
                  row["notes"], row["status"], row["created_at"]))
        for row in reviews:
            db.execute("""
                INSERT INTO fiscal_pending_reviews_new
                (review_id,owner_id,pending_id,candidate_classification,confirmed_jurisdiction,
                 reviewer_name,reviewer_role,professional_registration,evidence_reference,
                 reviewed_on,review_notes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (row["review_id"], owner_id, row["pending_id"],
                  row["candidate_classification"], row["confirmed_jurisdiction"],
                  row["reviewer_name"], row["reviewer_role"], row["professional_registration"],
                  row["evidence_reference"], row["reviewed_on"], row["review_notes"],
                  row["created_at"]))

        # Drop in child-first order, then atomically replace with the new layouts.
        for table in ("fiscal_pending_reviews", "fiscal_reserve_pending_foreign",
                      "fiscal_reserve_entries", "fiscal_reserve_settings"):
            if table in existing:
                db.execute(f'DROP TABLE "{table}"')
        for table in TABLES:
            db.execute(f'ALTER TABLE "{table}_new" RENAME TO "{table}"')

        db.execute("""
            CREATE INDEX IF NOT EXISTS fiscal_pending_reviews_item
            ON fiscal_pending_reviews(owner_id,pending_id,created_at DESC)
        """)
        db.execute("""
            INSERT OR IGNORE INTO fiscal_reserve_settings(owner_id,category,rate)
            VALUES(?, 'BR_DAY_TRADE', 20.0)
        """, (owner_id,))
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("Migração fiscal interrompida: integridade referencial inválida")
        db.commit()
        return owner_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
