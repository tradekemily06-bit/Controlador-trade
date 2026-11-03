import os
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema

OWNER = "test-owner"
os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = OWNER

def make_queue(path):
    queue = FiscalPendingQueue(str(path))
    migrate_fiscal_schema(str(path))
    return queue


def sample(reference="FOREIGN-STATEMENT-001"):
    return {
        "reference": reference,
        "original_amount": 125.50,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-10-30",
        "fx_rate": 5.42,
        "fx_date": "2026-10-30",
        "fx_source": "Banco Central - cotação informada",
    }


def test_foreign_item_is_persisted_as_pending_without_tax_calculation(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    item = queue.add(OWNER, sample())
    assert item["status"] == "PENDING_CLASSIFICATION"
    assert item["original_amount"] == 125.5
    assert item["original_currency"] == "USD"
    result = queue.list_pending(OWNER)
    assert result["total"] == 1
    assert result["items"][0]["reference"] == "FOREIGN-STATEMENT-001"
    assert "não integram os totais" in result["note"]


def test_duplicate_reference_is_rejected(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    queue.add(OWNER, sample())
    try:
        queue.add(OWNER, sample())
    except Exception as exc:
        assert "UNIQUE" in str(exc).upper()
    else:
        raise AssertionError("duplicate reference must be rejected")


def test_fx_evidence_must_be_complete(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = sample()
    payload["fx_source"] = ""
    try:
        queue.add(OWNER, payload)
    except ValueError as exc:
        assert "fx_date e fx_source" in str(exc)
    else:
        raise AssertionError("incomplete FX evidence must be rejected")


def test_invalid_amount_currency_and_date_are_rejected(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for key, value in (("original_amount", 0), ("original_currency", "XYZ"), ("occurred_on", "30/10/2026")):
        payload = sample()
        payload[key] = value
        try:
            queue.add(OWNER, payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {key} must be rejected")


def test_queue_is_separate_from_reserve_ledger(tmp_path):
    from finance.fiscal_reserve import FiscalReserve
    path = str(tmp_path / "fiscal.sqlite3")
    queue = make_queue(path)
    reserve = FiscalReserve(path)
    queue.add(OWNER, sample())
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0
    assert reserve.summary(OWNER)["periods"]["year"]["entries"] == 0


def test_pending_queue_pagination_returns_distinct_pages_and_total(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for number in range(7):
        queue.add(OWNER, sample(f"FOREIGN-PAGE-{number}"))

    first = queue.list_pending(OWNER, limit=3, offset=0)
    second = queue.list_pending(OWNER, limit=3, offset=3)
    last = queue.list_pending(OWNER, limit=3, offset=6)

    assert first["total"] == second["total"] == last["total"] == 7
    assert len(first["items"]) == 3
    assert len(second["items"]) == 3
    assert len(last["items"]) == 1
    references = [item["reference"] for page in (first, second, last) for item in page["items"]]
    assert len(references) == len(set(references)) == 7
    assert all(item["status"] == "PENDING_CLASSIFICATION" for page in (first, second, last) for item in page["items"])


def test_pending_queue_rejects_invalid_pagination(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for limit, offset in ((0, 0), (501, 0), (True, 0), (10, -1), (10, True)):
        try:
            queue.list_pending(OWNER, limit=limit, offset=offset)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid pending pagination must be rejected")


def review_sample():
    return {
        "candidate_classification": "ETF - revisar enquadramento",
        "confirmed_jurisdiction": "Estados Unidos",
        "reviewer_name": "Profissional de teste",
        "reviewer_role": "contador",
        "professional_registration": "CRC-TESTE-123",
        "evidence_reference": "Parecer interno REF-2026-001",
        "reviewed_on": "2026-11-03",
        "review_notes": "Registro de teste; não autoriza cálculo automático.",
    }


def test_professional_review_is_append_only_and_never_classifies_or_calculates(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    pending = queue.add(OWNER, sample())
    review = queue.record_review(OWNER, pending["pending_id"], review_sample())

    assert review["status_unchanged"] == "PENDING_CLASSIFICATION"
    assert review["reserve_calculated"] is False
    assert review["tax_rate_available"] is False
    assert queue.list_reviews(OWNER, pending["pending_id"])[0]["review_id"] == review["review_id"]
    assert queue.list_pending(OWNER)["items"][0]["status"] == "PENDING_CLASSIFICATION"


def test_review_requires_professional_identity_and_evidence(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    pending = queue.add(OWNER, sample())
    for key in ("reviewer_name", "professional_registration", "evidence_reference"):
        payload = review_sample()
        payload[key] = ""
        try:
            queue.record_review(OWNER, pending["pending_id"], payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{key} must be required")


def test_review_rejects_unqualified_role_and_invalid_date(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    pending = queue.add(OWNER, sample())
    for key, value in (("reviewer_role", "trader"), ("reviewed_on", "03/11/2026")):
        payload = review_sample()
        payload[key] = value
        try:
            queue.record_review(OWNER, pending["pending_id"], payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {key} must be rejected")


def test_review_for_unknown_pending_item_is_rejected(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    try:
        queue.record_review(OWNER, "missing-id", review_sample())
    except ValueError as exc:
        assert "não encontrada" in str(exc)
    else:
        raise AssertionError("unknown pending item must be rejected")


def test_review_foreign_key_is_enforced_and_prevents_orphaning(tmp_path):
    import sqlite3

    path = str(tmp_path / "fiscal.sqlite3")
    queue = make_queue(path)
    pending = queue.add(OWNER, sample())
    queue.record_review(OWNER, pending["pending_id"], review_sample())

    with queue._connect() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        try:
            db.execute(
                "DELETE FROM fiscal_reserve_pending_foreign WHERE pending_id = ?",
                (pending["pending_id"],),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("pending item with review history must not be deleted")


def test_pending_amount_and_fx_rate_reject_boolean_values(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for key in ("original_amount", "fx_rate"):
        payload = sample()
        payload[key] = True
        try:
            queue.add(OWNER, payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"boolean must not be accepted for {key}")
