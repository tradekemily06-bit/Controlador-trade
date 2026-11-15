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


def _install_append_only_review_triggers(db: sqlite3.Connection) -> None:
    """Install immutable review-history guards as part of the schema transaction."""
    trigger_specs = (
        ("fiscal_pending_reviews", "fiscal_pending_reviews_no_update", "UPDATE"),
        ("fiscal_pending_reviews", "fiscal_pending_reviews_no_delete", "DELETE"),
        ("fiscal_domestic_pending_reviews", "fiscal_domestic_pending_reviews_no_update", "UPDATE"),
        ("fiscal_domestic_pending_reviews", "fiscal_domestic_pending_reviews_no_delete", "DELETE"),
    )
    for table, trigger, operation in trigger_specs:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            continue
        db.execute(
            f"CREATE TRIGGER IF NOT EXISTS {trigger} "
            f"BEFORE {operation} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'fiscal review history is append-only'); END"
        )


def _has_unique_index(db: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> bool:
    """Return whether an exact ordered UNIQUE index/primary key exists."""
    for index in db.execute(f'PRAGMA index_list("{table}")').fetchall():
        # A partial UNIQUE index protects only rows matching its WHERE clause;
        # it cannot enforce owner-scoped uniqueness for the complete table.
        if not index["unique"] or index["partial"]:
            continue
        indexed_columns = tuple(row["name"] for row in db.execute(f'PRAGMA index_info("{index["name"]}")').fetchall())
        if indexed_columns == columns:
            return True
    return False


def _has_composite_review_foreign_key(db: sqlite3.Connection) -> bool:
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in db.execute('PRAGMA foreign_key_list("fiscal_pending_reviews")').fetchall():
        grouped.setdefault(int(row["id"]), []).append(row)
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda row: int(row["seq"]))
        if (len(ordered) == 2 and ordered[0]["table"] == "fiscal_reserve_pending_foreign"
            and [(row["from"], row["to"]) for row in ordered] == [("owner_id", "owner_id"), ("pending_id", "pending_id")]
            and all(str(row["on_delete"]).upper() == "RESTRICT" for row in ordered)):
            return True
    return False


def _has_composite_foreign_key(db: sqlite3.Connection, child: str, parent: str, pairs: tuple[tuple[str, str], ...]) -> bool:
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in db.execute(f'PRAGMA foreign_key_list("{child}")').fetchall():
        grouped.setdefault(int(row["id"]), []).append(row)
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda row: int(row["seq"]))
        if len(ordered) == len(pairs) and ordered[0]["table"] == parent:
            if (tuple((row["from"], row["to"]) for row in ordered) == pairs
                and all(str(row["on_delete"]).upper() == "RESTRICT" for row in ordered)):
                return True
    return False


def _domestic_schema_constraints_valid(db: sqlite3.Connection) -> bool:
    return (
        _has_unique_index(db, "fiscal_reserve_pending_domestic", ("owner_id", "reference"))
        and _has_unique_index(db, "fiscal_reserve_pending_domestic", ("owner_id", "pending_id"))
        and _has_composite_foreign_key(db, "fiscal_domestic_pending_reviews", "fiscal_reserve_pending_domestic", (("owner_id", "owner_id"), ("pending_id", "pending_id")))
    )

def _owner_schema_constraints_valid(db: sqlite3.Connection) -> bool:
    return (
        _has_unique_index(db, "fiscal_reserve_settings", ("owner_id", "category"))
        and _has_unique_index(db, "fiscal_reserve_entries", ("owner_id", "category", "reference"))
        and _has_unique_index(db, "fiscal_reserve_pending_foreign", ("owner_id", "pending_id"))
        and _has_unique_index(db, "fiscal_reserve_pending_foreign", ("owner_id", "reference"))
        and _has_composite_review_foreign_key(db)
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
        # A partial rebuild must never silently reassign rows that already
        # carry an owner. Legacy rows without owner_id can be adopted only when
        # no persisted owner identity exists in the fiscal tables.
        for table in TABLES:
            if table not in existing:
                continue
            columns = {row["name"] for row in db.execute(f'PRAGMA table_info("{table}")')}
            if "owner_id" not in columns:
                continue
            null_owners = int(db.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE owner_id IS NULL'
            ).fetchone()[0])
            if null_owners:
                raise RuntimeError(
                    f"A tabela fiscal {table} contém registros sem proprietário; "
                    "migração automática bloqueada para evitar atribuição indevida."
                )
            table_owners = {
                row[0] for row in db.execute(
                    f'SELECT DISTINCT owner_id FROM "{table}"'
                ).fetchall()
            }
            if table_owners and table_owners != {owner_id}:
                raise RuntimeError(
                    f"A identidade fiscal configurada não corresponde ao proprietário já gravado em {table}; "
                    "migração automática entre proprietários foi bloqueada."
                )
        if "fiscal_reserve_pending_domestic" in existing:
            domestic_columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_reserve_pending_domestic)")}
            if "owner_id" not in domestic_columns:
                raise RuntimeError("A fila brasileira pendente não possui identidade proprietária; acesso bloqueado.")
            if db.execute(
                "SELECT 1 FROM fiscal_reserve_pending_domestic WHERE owner_id IS NULL LIMIT 1"
            ).fetchone():
                raise RuntimeError("A fila brasileira pendente contém registros sem proprietário; acesso bloqueado.")
            domestic_owners = {row[0] for row in db.execute(
                "SELECT DISTINCT owner_id FROM fiscal_reserve_pending_domestic WHERE owner_id IS NOT NULL"
            ).fetchall()}
            if domestic_owners and domestic_owners != {owner_id}:
                raise RuntimeError("A identidade fiscal configurada não corresponde ao proprietário da fila brasileira; migração automática bloqueada.")
        if "fiscal_domestic_pending_reviews" in existing:
            review_columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_domestic_pending_reviews)")}
            if "owner_id" not in review_columns:
                raise RuntimeError("A revisão brasileira pendente não possui identidade proprietária; acesso bloqueado.")
            if db.execute(
                "SELECT 1 FROM fiscal_domestic_pending_reviews WHERE owner_id IS NULL LIMIT 1"
            ).fetchone():
                raise RuntimeError("A revisão brasileira pendente contém registros sem proprietário; acesso bloqueado.")
            review_owners = {row[0] for row in db.execute(
                "SELECT DISTINCT owner_id FROM fiscal_domestic_pending_reviews WHERE owner_id IS NOT NULL"
            ).fetchall()}
            if review_owners and review_owners != {owner_id}:
                raise RuntimeError("A identidade fiscal configurada não corresponde às revisões brasileiras; migração automática bloqueada.")
        domestic_table_names = {
            "fiscal_reserve_pending_domestic", "fiscal_domestic_pending_reviews"
        }
        domestic_tables_present = domestic_table_names.issubset(existing)
        if domestic_table_names.intersection(existing) and not domestic_tables_present:
            raise RuntimeError(
                "Esquema da fila brasileira pendente incompleto: tabela relacionada ausente; "
                "acesso bloqueado para preservar os dados."
            )
        if domestic_tables_present and not _domestic_schema_constraints_valid(db):
            raise RuntimeError(
                "Esquema da fila brasileira pendente inválido: restrições de proprietário ou "
                "chave estrangeira composta ausentes; acesso bloqueado para preservar os dados."
            )
        if all(table in existing for table in TABLES):
            owner_columns = {
                table: {row["name"] for row in db.execute(f'PRAGMA table_info("{table}")')}
                for table in TABLES
            }
            if all("owner_id" in columns for columns in owner_columns.values()):
                settings_columns = owner_columns["fiscal_reserve_settings"]
                if "rate_source" not in settings_columns:
                    db.execute(
                        "ALTER TABLE fiscal_reserve_settings ADD COLUMN rate_source "
                        "TEXT NOT NULL DEFAULT 'LEGACY_UNKNOWN' "
                        "CHECK(rate_source IN ('DEFAULT','USER_CONFIGURED','LEGACY_UNKNOWN'))"
                    )
                # owner_id columns alone do not guarantee owner-scoped uniqueness or review linkage.
                constraints_valid = _owner_schema_constraints_valid(db)
                pending_columns = owner_columns["fiscal_reserve_pending_foreign"]
                if "original_result" not in pending_columns:
                    db.execute("ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN original_result REAL")
                if "record_kind" not in pending_columns:
                    db.execute("ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN record_kind TEXT NOT NULL DEFAULT 'ASSET_AMOUNT'")
                for column in ("tax_residency_at_event", "income_nature", "event_type", "fx_conversion_method"):
                    if column not in pending_columns:
                        db.execute(f"ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN {column} TEXT NOT NULL DEFAULT 'NOT_INFORMED'")
                for column, declaration in (
                    ("institution", "TEXT NOT NULL DEFAULT ''"),
                    ("custody_location", "TEXT NOT NULL DEFAULT 'NOT_INFORMED'"),
                    ("contract_type", "TEXT NOT NULL DEFAULT 'NOT_INFORMED'"),
                    ("acquisition_cost", "REAL CHECK(acquisition_cost IS NULL OR (acquisition_cost >= 0 AND acquisition_cost <= 1000000000000.0))"),
                    ("transaction_fees", "REAL CHECK(transaction_fees IS NULL OR (transaction_fees >= 0 AND transaction_fees <= 1000000000000.0))"),
                    ("foreign_tax_paid", "REAL CHECK(foreign_tax_paid IS NULL OR (foreign_tax_paid >= 0 AND foreign_tax_paid <= 1000000000000.0))"),
                ):
                    if column not in pending_columns:
                        db.execute(
                            f"ALTER TABLE fiscal_reserve_pending_foreign ADD COLUMN {column} {declaration}"
                        )
                stored_owners = set()
                scoped_tables = list(TABLES)
                if "fiscal_reserve_pending_domestic" in existing:
                    domestic_columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_reserve_pending_domestic)")}
                    if "owner_id" not in domestic_columns:
                        raise RuntimeError("A fila brasileira pendente não possui identidade proprietária; acesso bloqueado.")
                    scoped_tables.append("fiscal_reserve_pending_domestic")
                if "fiscal_domestic_pending_reviews" in existing:
                    review_columns = {row["name"] for row in db.execute("PRAGMA table_info(fiscal_domestic_pending_reviews)")}
                    if "owner_id" not in review_columns:
                        raise RuntimeError("A revisão brasileira pendente não possui identidade proprietária; acesso bloqueado.")
                    scoped_tables.append("fiscal_domestic_pending_reviews")
                for table in scoped_tables:
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
                # Repair a missing default planning rate in already owner-scoped
                # databases without overwriting a rate the owner has configured.
                db.execute(
                    """INSERT OR IGNORE INTO fiscal_reserve_settings
                       (owner_id, category, rate, rate_source)
                       VALUES (?, 'BR_DAY_TRADE', 20.0, 'DEFAULT')""",
                    (owner_id,),
                )
                db.execute(
                    """INSERT OR IGNORE INTO fiscal_reserve_settings
                       (owner_id, category, rate, rate_source)
                       VALUES (?, 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT', 15.0, 'DEFAULT')""",
                    (owner_id,),
                )
                violations = db.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        "Migração fiscal interrompida: integridade referencial inválida no esquema existente"
                    )
                if constraints_valid:
                    _install_append_only_review_triggers(db)
                    db.commit()
                    return owner_id
                # Rebuild atomically when owner-scoped constraints are incomplete.

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
                rate_source TEXT NOT NULL DEFAULT 'LEGACY_UNKNOWN'
                    CHECK(rate_source IN ('DEFAULT','USER_CONFIGURED','LEGACY_UNKNOWN')),
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
                tax_residency_at_event TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                income_nature TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                event_type TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                fx_conversion_method TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                institution TEXT NOT NULL DEFAULT '',
                custody_location TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                contract_type TEXT NOT NULL DEFAULT 'NOT_INFORMED',
                acquisition_cost REAL CHECK(acquisition_cost IS NULL OR (acquisition_cost >= 0 AND acquisition_cost <= 1000000000000.0)),
                transaction_fees REAL CHECK(transaction_fees IS NULL OR (transaction_fees >= 0 AND transaction_fees <= 1000000000000.0)),
                foreign_tax_paid REAL CHECK(foreign_tax_paid IS NULL OR (foreign_tax_paid >= 0 AND foreign_tax_paid <= 1000000000000.0)),
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
            rate_source = row["rate_source"] if "rate_source" in keys else "LEGACY_UNKNOWN"
            if rate_source not in {"DEFAULT", "USER_CONFIGURED", "LEGACY_UNKNOWN"}:
                raise RuntimeError("Origem do percentual fiscal inválida; migração interrompida.")
            db.execute(
                "INSERT INTO fiscal_reserve_settings_new(owner_id,category,rate,rate_source) VALUES(?,?,?,?)",
                (owner_id, row["category"], row["rate"], rate_source),
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
            # Preserve signed realized results and record kind when recovering a
            # partially migrated owner schema. Older rows receive safe defaults.
            pending_columns = set(row.keys())
            original_result = row["original_result"] if "original_result" in pending_columns else None
            record_kind = row["record_kind"] if "record_kind" in pending_columns else "ASSET_AMOUNT"
            declared = {name: row[name] if name in pending_columns and row[name] else "NOT_INFORMED" for name in ("tax_residency_at_event", "income_nature", "event_type", "fx_conversion_method")}
            db.execute("""
                INSERT INTO fiscal_reserve_pending_foreign_new
                (pending_id,owner_id,reference,original_amount,original_currency,instrument,
                 jurisdiction,occurred_on,fx_rate,fx_date,fx_source,notes,status,
                 original_result,record_kind,tax_residency_at_event,income_nature,event_type,fx_conversion_method,
                 institution,custody_location,contract_type,acquisition_cost,transaction_fees,foreign_tax_paid,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (row["pending_id"], owner_id, row["reference"], row["original_amount"],
                  row["original_currency"], row["instrument"], row["jurisdiction"],
                  row["occurred_on"], row["fx_rate"], row["fx_date"], row["fx_source"],
                  row["notes"], row["status"], original_result, record_kind, declared["tax_residency_at_event"],
                  declared["income_nature"], declared["event_type"], declared["fx_conversion_method"],
                  row["institution"] if "institution" in pending_columns else "",
                  row["custody_location"] if "custody_location" in pending_columns else "NOT_INFORMED",
                  row["contract_type"] if "contract_type" in pending_columns else "NOT_INFORMED",
                  row["acquisition_cost"] if "acquisition_cost" in pending_columns else None,
                  row["transaction_fees"] if "transaction_fees" in pending_columns else None,
                  row["foreign_tax_paid"] if "foreign_tax_paid" in pending_columns else None,
                  row["created_at"]))
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
            INSERT OR IGNORE INTO fiscal_reserve_settings(owner_id,category,rate,rate_source)
            VALUES(?, 'BR_DAY_TRADE', 20.0, 'DEFAULT')
        """, (owner_id,))
        db.execute("""
            INSERT OR IGNORE INTO fiscal_reserve_settings(owner_id,category,rate,rate_source)
            VALUES(?, 'BR_RESIDENT_FOREIGN_FINANCIAL_INVESTMENT', 15.0, 'DEFAULT')
        """, (owner_id,))
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("Migração fiscal interrompida: integridade referencial inválida")
        _install_append_only_review_triggers(db)
        db.commit()
        return owner_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
