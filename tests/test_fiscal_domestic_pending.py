from datetime import date

import pytest

from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def sample(reference="BR-PENDING-001"):
    return {
        "reference": reference,
        "category_candidate": "BR_COMMON_EXCHANGE",
        "instrument": "Ação / ETF",
        "market_scope": "B3",
        "occurred_on": "2026-11-03",
        "realized_result_brl": -125.75,
        "notes": "Aguardando classificação documental.",
    }


def test_domestic_pending_is_separate_from_foreign_queue_and_reserve(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner-a")
    path = str(tmp_path / "fiscal.sqlite3")
    queue = FiscalDomesticPendingQueue(path)
    owner_id = migrate_fiscal_schema(path)
    queue.add(owner_id, sample())
    reserve = FiscalReserve(path)

    assert queue.list_pending(owner_id)["total"] == 1
    assert reserve.summary(owner_id)["total_reserved_brl"] == 0


def test_domestic_pending_keeps_signed_result_but_never_calculates_reserve(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    item = queue.add("owner-a", sample())

    assert item["realized_result_brl"] == -125.75
    assert item["status"] == "PENDING_CLASSIFICATION"
    listing = queue.list_pending("owner-a")
    assert listing["items"][0]["realized_result_brl"] == -125.75
    assert listing["included_in_totals"] is False
    assert listing["reserve_calculated"] is False


def test_domestic_pending_owner_scope_and_duplicate_reference(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    queue.add("owner-a", sample())
    assert queue.list_pending("owner-b")["total"] == 0
    with pytest.raises(Exception):
        queue.add("owner-a", sample())


def test_domestic_pending_rejects_unknown_and_foreign_category_candidates(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    unknown = sample("BR-UNKNOWN-CATEGORY")
    unknown["category_candidate"] = "BR_FAKE_TAX_CATEGORY"
    with pytest.raises(ValueError, match="catálogo brasileiro permitido"):
        queue.add("owner-a", unknown)

    foreign = sample("BR-FOREIGN-CATEGORY")
    foreign["category_candidate"] = "FOREIGN_CRYPTO"
    with pytest.raises(ValueError, match="catálogo brasileiro permitido"):
        queue.add("owner-a", foreign)

    unspecified = sample("BR-UNSPECIFIED-CATEGORY")
    unspecified["category_candidate"] = ""
    assert queue.add("owner-a", unspecified)["category_candidate"] == ""


def test_domestic_pending_validates_date_and_rejects_boolean_result(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    bad_date = sample("BR-BAD-DATE")
    bad_date["occurred_on"] = "03/11/2026"
    with pytest.raises(ValueError):
        queue.add("owner-a", bad_date)
    bad_result = sample("BR-BAD-RESULT")
    bad_result["realized_result_brl"] = True
    with pytest.raises(ValueError):
        queue.add("owner-a", bad_result)


def test_domestic_pending_summary_has_day_week_month_year_counts_only(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    queue.add("owner-a", sample())
    summary = queue.summary("owner-a", as_of=date(2026, 11, 3))
    assert summary["total"] == 1
    assert set(summary["periods"]) == {"day", "week", "month", "year"}
    assert summary["periods"]["day"]["results"] == 1
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False


def test_domestic_pending_summary_respects_all_calendar_boundaries(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "domestic-period-boundaries.sqlite3"))
    dates = (
        ("BR-DAY", "2026-11-03", 10.0),
        ("BR-WEEK", "2026-11-02", 0.0),
        ("BR-MONTH", "2026-10-31", None),
        ("BR-YEAR", "2025-12-31", -5.0),
    )
    for reference, occurred_on, result in dates:
        payload = sample(reference)
        payload["occurred_on"] = occurred_on
        payload.pop("realized_result_brl", None)
        if result is not None:
            payload["realized_result_brl"] = result
        queue.add("owner-a", payload)

    summary = queue.summary("owner-a", as_of=date(2026, 11, 3))

    assert summary["total"] == 4
    assert summary["periods"]["day"]["total"] == 1
    assert summary["periods"]["day"]["results"] == 1
    assert summary["periods"]["week"]["total"] == 2
    assert summary["periods"]["week"]["results"] == 2
    assert summary["periods"]["month"]["total"] == 2
    assert summary["periods"]["month"]["results"] == 2
    assert summary["periods"]["year"]["total"] == 3
    assert summary["periods"]["year"]["results"] == 3
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False

def test_domestic_pending_supports_shared_in_memory_database():
    queue = FiscalDomesticPendingQueue()
    queue.add("owner-a", sample())
    assert queue.list_pending("owner-a")["total"] == 1


def review_payload():
    return {
        "candidate_classification": "BR_COMMON_EXCHANGE",
        "confirmed_jurisdiction": "Brasil",
        "reviewer_name": "Profissional declarado",
        "reviewer_role": "Contador",
        "professional_registration": "CRC-DECLARADO",
        "evidence_reference": "DOC-REVISAO-001",
        "reviewed_on": "2026-11-04",
        "review_notes": "Registro de revisão para auditoria; identidade e registro não foram verificados pelo sistema.",
    }


def test_domestic_pending_review_is_auditable_but_does_not_classify_or_book(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "domestic-review.sqlite3"))
    item = queue.add("owner-a", sample())

    review = queue.record_review("owner-a", item["pending_id"], review_payload())

    assert review["reviewer_identity_status"] == "DECLARED_NOT_VERIFIED"
    assert review["professional_registration_verified"] is False
    assert review["status_unchanged"] == "PENDING_CLASSIFICATION"
    assert review["reserve_calculated"] is False
    assert review["tax_rate_available"] is False
    reviews = queue.list_reviews("owner-a", item["pending_id"])
    assert len(reviews) == 1
    assert reviews[0]["evidence_reference"] == "DOC-REVISAO-001"
    assert reviews[0]["reviewer_identity_status"] == "DECLARED_NOT_VERIFIED"
    assert queue.list_pending("owner-a")["items"][0]["status"] == "PENDING_CLASSIFICATION"

    invalid = review_payload()
    invalid["candidate_classification"] = "FOREIGN_CRYPTO"
    with pytest.raises(ValueError, match="catálogo brasileiro permitido"):
        queue.record_review("owner-a", item["pending_id"], invalid)


def test_domestic_pending_review_is_owner_scoped_and_rejects_unqualified_role(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "domestic-review-scope.sqlite3"))
    item = queue.add("owner-a", sample())

    with pytest.raises(ValueError):
        queue.record_review("owner-b", item["pending_id"], review_payload())
    with pytest.raises(ValueError):
        queue.list_reviews("owner-b", item["pending_id"])

    invalid = review_payload()
    invalid["reviewer_role"] = "proprietário"
    with pytest.raises(ValueError):
        queue.record_review("owner-a", item["pending_id"], invalid)


def test_domestic_pending_rejects_missing_or_invalid_owner_for_every_operation(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "owner-required.sqlite3"))
    item = queue.add("owner-a", sample("OWNER-VALID"))
    invalid_owners = ("", "   ", "x" * 161)
    for owner in invalid_owners:
        operations = (
            lambda owner=owner: queue.add(owner, sample("OWNER-INVALID-" + str(len(owner)))),
            lambda owner=owner: queue.list_pending(owner),
            lambda owner=owner: queue.summary(owner),
            lambda owner=owner: queue.record_review(owner, item["pending_id"], review_payload()),
            lambda owner=owner: queue.list_reviews(owner, item["pending_id"]),
        )
        for operation in operations:
            with pytest.raises(ValueError, match="identidade proprietária"):
                operation()



def test_domestic_and_foreign_review_catalogs_are_disjoint():
    from finance.fiscal_pending_queue import FOREIGN_REVIEW_CANDIDATES
    from finance.fiscal_taxonomy import BRAZIL_CATEGORIES

    assert set(BRAZIL_CATEGORIES).isdisjoint(FOREIGN_REVIEW_CANDIDATES)


def test_domestic_review_rejects_coerced_non_text_fields(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "strict-domestic-review.sqlite3"))
    item = queue.add("owner-a", sample())
    for field in (
        "candidate_classification", "confirmed_jurisdiction", "reviewer_name",
        "reviewer_role", "professional_registration", "evidence_reference", "review_notes",
    ):
        payload = review_payload()
        payload[field] = ["texto", "indevido"]
        with pytest.raises(ValueError, match="deve ser texto"):
            queue.record_review("owner-a", item["pending_id"], payload)

    with pytest.raises(ValueError, match="pending_id inválido"):
        queue.record_review("owner-a", 123, review_payload())
    with pytest.raises(ValueError, match="pending_id inválido"):
        queue.list_reviews("owner-a", 123)


def test_domestic_review_rejects_future_review_date(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "future-domestic-review.sqlite3"))
    item = queue.add("owner-a", sample("BR-FUTURE-REVIEW"))
    payload = review_payload()
    payload["reviewed_on"] = "9999-12-31"
    with pytest.raises(ValueError, match="reviewed_on não pode estar no futuro"):
        queue.record_review("owner-a", item["pending_id"], payload)
    assert queue.list_reviews("owner-a", item["pending_id"]) == []


def test_domestic_pending_rejects_non_text_intake_fields(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "strict-domestic-intake.sqlite3"))
    for field in ("reference", "instrument", "category_candidate", "market_scope", "occurred_on", "notes"):
        payload = sample("BR-STRICT-" + field.upper())
        payload[field] = ["valor", "indevido"]
        with pytest.raises(ValueError, match="deve ser texto"):
            queue.add("owner-a", payload)
    assert queue.list_pending("owner-a")["total"] == 0


@pytest.mark.parametrize("value", ["125.75", True, [], {}, float("nan"), float("inf")])
def test_domestic_pending_rejects_coerced_or_nonfinite_results(tmp_path, value):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "strict-domestic-money.sqlite3"))
    payload = sample("BR-STRICT-MONEY")
    payload["realized_result_brl"] = value
    with pytest.raises(ValueError, match="realized_result_brl"):
        queue.add("owner-a", payload)
    assert queue.list_pending("owner-a")["total"] == 0



def test_domestic_pending_rejects_out_of_range_pagination_offsets(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "domestic-pagination.sqlite3"))
    queue.add("owner-a", sample("BR-PAGE-BOUNDARY"))

    for offset in (-1, True, 1_000_000_001, 2**63):
        with pytest.raises(ValueError, match="offset deve estar entre"):
            queue.list_pending("owner-a", limit=10, offset=offset)

    page = queue.list_pending("owner-a", limit=10, offset=1_000_000_000)
    assert page["offset"] == 1_000_000_000
    assert page["items"] == []
    assert page["total"] == 1


def test_domestic_pending_rejects_non_text_owner_identity(tmp_path):
    queue = FiscalDomesticPendingQueue(str(tmp_path / "strict-domestic-owner.sqlite3"))
    for invalid_owner in (None, 123, True, [], {}, object()):
        with pytest.raises(ValueError, match="identidade proprietária"):
            queue.list_pending(invalid_owner)
