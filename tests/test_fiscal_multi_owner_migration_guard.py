from __future__ import annotations

import sqlite3

import pytest

from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_identity import configured_fiscal_owner_id
from finance.fiscal_schema import migrate_fiscal_schema


def test_migration_refuses_multiple_owners_in_core_fiscal_ledger_without_mutation(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "multi-owner-core.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "configured-owner")
    configured_owner = migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        db.execute(
            """
            INSERT INTO fiscal_reserve_entries
            (entry_id, owner_id, category, entry_type, realized_result_brl,
             reserve_rate, reserve_amount_brl, reference, occurred_on, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "other-owner-entry", "tenant-b-subject-b", "BR_DAY_TRADE",
                "REALIZED_RESULT", 100.0, 20.0, 20.0, "other-owner-ref",
                "2026-11-20", "2026-11-20T00:00:00+00:00", "",
            ),
        )
        before = db.execute(
            "SELECT entry_id, owner_id, reference FROM fiscal_reserve_entries ORDER BY entry_id"
        ).fetchall()
        schema_before = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall()

    with pytest.raises(RuntimeError, match="não corresponde ao proprietário"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        after = db.execute(
            "SELECT entry_id, owner_id, reference FROM fiscal_reserve_entries ORDER BY entry_id"
        ).fetchall()
        schema_after = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall()

    assert configured_owner != "tenant-b-subject-b"
    assert after == before
    assert schema_after == schema_before


def test_migration_refuses_multiple_owners_in_domestic_queue_without_mutation(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "multi-owner-domestic.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "configured-owner")
    migrate_fiscal_schema(path)
    configured_owner = configured_fiscal_owner_id()

    queue = FiscalDomesticPendingQueue(path)
    queue.add(configured_owner, {
        "reference": "configured-owner-item",
        "instrument": "ETF",
        "occurred_on": "2026-11-20",
    })
    queue.add("tenant-b-subject-b", {
        "reference": "other-owner-item",
        "instrument": "ETF",
        "occurred_on": "2026-11-20",
    })

    with sqlite3.connect(path) as db:
        before = db.execute(
            "SELECT pending_id, owner_id, reference FROM fiscal_reserve_pending_domestic ORDER BY reference"
        ).fetchall()
        schema_before = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall()

    with pytest.raises(RuntimeError, match="identidade fiscal configurada não corresponde"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        after = db.execute(
            "SELECT pending_id, owner_id, reference FROM fiscal_reserve_pending_domestic ORDER BY reference"
        ).fetchall()
        schema_after = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall()

    assert after == before
    assert schema_after == schema_before


def test_migration_refuses_multiple_owners_in_foreign_queue_and_review_history_without_mutation(
    tmp_path, monkeypatch
):
    from finance.fiscal_pending_queue import FiscalPendingQueue

    path = str(tmp_path / "multi-owner-foreign.sqlite3")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "configured-owner")
    migrate_fiscal_schema(path)
    queue = FiscalPendingQueue(path)

    base = {
        "original_amount": 125.50,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-20",
        "fx_rate": 5.42,
        "fx_date": "2026-11-20",
        "fx_source": "Documento de teste",
        "fx_conversion_method": "PTAX_SELL",
    }
    queue.add("tenant-b-subject-b", {**base, "reference": "FOREIGN-OTHER-OWNER"})
    pending = queue.list_pending("tenant-b-subject-b")["items"][0]
    queue.record_review("tenant-b-subject-b", pending["pending_id"], {
        "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
        "confirmed_jurisdiction": "US",
        "reviewer_name": "Reviewer Test",
        "reviewer_role": "contador",
        "professional_registration": "CRC-TEST-1",
        "evidence_reference": "DOC-TEST-1",
        "reviewed_on": "2026-11-20",
    })

    with sqlite3.connect(path) as db:
        pending_before = db.execute(
            "SELECT pending_id, owner_id, reference FROM fiscal_reserve_pending_foreign ORDER BY reference"
        ).fetchall()
        reviews_before = db.execute(
            "SELECT review_id, owner_id, pending_id FROM fiscal_pending_reviews ORDER BY review_id"
        ).fetchall()
        schema_before = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall()

    with pytest.raises(RuntimeError, match="não corresponde ao proprietário"):
        migrate_fiscal_schema(path)

    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT pending_id, owner_id, reference FROM fiscal_reserve_pending_foreign ORDER BY reference"
        ).fetchall() == pending_before
        assert db.execute(
            "SELECT review_id, owner_id, pending_id FROM fiscal_pending_reviews ORDER BY review_id"
        ).fetchall() == reviews_before
        assert db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') ORDER BY type, name"
        ).fetchall() == schema_before
