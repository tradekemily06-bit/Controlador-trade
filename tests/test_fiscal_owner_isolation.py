import os
import sqlite3

import pytest

from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def test_reserve_and_pending_queue_are_isolated_by_owner(tmp_path, monkeypatch):
    path = tmp_path / "fiscal.sqlite3"
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "primary-owner")
    reserve = FiscalReserve(str(path))
    queue = FiscalPendingQueue(str(path))
    owner_a = migrate_fiscal_schema(str(path))
    owner_b = "single:separate-test-owner"

    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO fiscal_reserve_settings(owner_id,category,rate) VALUES(?,?,?)",
            (owner_b, "BR_DAY_TRADE", 10.0),
        )

    result_a = reserve.record_realized_result(owner_a, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "SAME-REFERENCE",
    })
    result_b = reserve.record_realized_result(owner_b, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 500,
        "reference": "SAME-REFERENCE",
    })
    assert result_a["reserve_amount_brl"] == 200
    assert result_b["reserve_amount_brl"] == 50
    assert reserve.summary(owner_a)["total_reserved_brl"] == 200
    assert reserve.summary(owner_b)["total_reserved_brl"] == 50

    payload = {
        "reference": "SAME-PENDING-REFERENCE",
        "original_amount": 100,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-03",
    }
    pending_a = queue.add(owner_a, payload)
    pending_b = queue.add(owner_b, payload)
    assert queue.list_pending(owner_a)["total"] == 1
    assert queue.list_pending(owner_b)["total"] == 1

    review_payload = {
        "candidate_classification": "ETF",
        "confirmed_jurisdiction": "US",
        "reviewer_name": "Revisor",
        "reviewer_role": "contador",
        "professional_registration": "CRC-TEST",
        "evidence_reference": "DOC-TEST",
        "reviewed_on": "2026-11-03",
    }
    queue.record_review(owner_a, pending_a["pending_id"], review_payload)
    with pytest.raises(ValueError, match="pendência não encontrada"):
        queue.record_review(owner_b, pending_a["pending_id"], review_payload)
    with pytest.raises(ValueError, match="pendência não encontrada"):
        queue.list_reviews(owner_b, pending_a["pending_id"])
    assert queue.list_reviews(owner_a, pending_a["pending_id"])
    assert pending_a["pending_id"] != pending_b["pending_id"]
