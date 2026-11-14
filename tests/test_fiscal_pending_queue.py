import os

import pytest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema

os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "test-owner"
from finance.fiscal_identity import configured_fiscal_owner_id
OWNER = configured_fiscal_owner_id()

def make_queue(path):
    FiscalPendingQueue(str(path))
    migrate_fiscal_schema(str(path))
    # Re-open after migration so constructor-installed append-only triggers
    # exist on the final owner-scoped review table, not the legacy table.
    return FiscalPendingQueue(str(path))


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
        "fx_conversion_method": "PTAX_SELL",
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


def test_documented_fx_is_converted_for_planning_without_entering_reserve(tmp_path):
    from finance.fiscal_reserve import FiscalReserve

    path = str(tmp_path / "fiscal-fx-preview.sqlite3")
    queue = make_queue(path)
    reserve = FiscalReserve(path)
    payload = sample("FOREIGN-FX-ASSET-001")
    payload.update({
        "acquisition_cost": 100.0,
        "transaction_fees": 2.5,
        "foreign_tax_paid": 1.25,
    })

    created = queue.add(OWNER, payload)
    assert created["fx_conversion_status"] == "CONVERTED_FOR_PLANNING_ONLY"
    assert created["fx_rate_direction"] == "BRL_PER_ORIGINAL_CURRENCY_UNIT"
    assert created["converted_amount_brl_for_planning"] == 680.21
    assert created["converted_acquisition_cost_brl_for_planning"] == 542.0
    assert created["converted_transaction_fees_brl_for_planning"] == 13.55
    assert created["converted_foreign_tax_paid_brl_for_planning"] == 6.78

    listed = queue.list_pending(OWNER)["items"][0]
    assert listed["converted_amount_brl_for_planning"] == 680.21
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0.0


def test_documented_fx_converts_signed_foreign_result_and_preserves_sign(tmp_path):
    queue = make_queue(tmp_path / "fiscal-fx-result.sqlite3")
    payload = sample("FOREIGN-FX-RESULT-001")
    payload.pop("original_amount")
    payload["original_result"] = -12.5

    created = queue.add_realized_result(OWNER, payload)

    assert created["converted_result_brl_for_planning"] == -67.75
    assert created["converted_amount_brl_for_planning"] is None
    assert created["fx_conversion_status"] == "CONVERTED_FOR_PLANNING_ONLY"


def test_foreign_item_without_documented_fx_stays_unconverted(tmp_path):
    queue = make_queue(tmp_path / "fiscal-fx-missing.sqlite3")
    payload = sample("FOREIGN-FX-MISSING-001")
    payload.update({
        "fx_rate": None,
        "fx_date": None,
        "fx_source": "",
        "fx_conversion_method": "NOT_CONVERTED",
    })

    created = queue.add(OWNER, payload)

    assert created["fx_conversion_status"] == "FX_NOT_PROVIDED"
    assert created["converted_amount_brl_for_planning"] is None


def test_brl_item_needs_no_fx_quote_for_planning_preview(tmp_path):
    queue = make_queue(tmp_path / "fiscal-fx-brl.sqlite3")
    payload = sample("FOREIGN-FX-BRL-001")
    payload.update({
        "original_currency": "BRL",
        "fx_rate": None,
        "fx_date": None,
        "fx_source": "",
        "fx_conversion_method": "NOT_INFORMED",
    })

    created = queue.add(OWNER, payload)

    assert created["fx_conversion_status"] == "ALREADY_BRL"
    assert created["converted_amount_brl_for_planning"] == 125.5


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
    for key, value in (("original_amount", 0), ("original_currency", "US1"), ("occurred_on", "30/10/2026")):
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
    for limit, offset in ((0, 0), (501, 0), (True, 0), (10, -1), (10, True), (10, 1_000_000_001), (10, 2**63)):
        try:
            queue.list_pending(OWNER, limit=limit, offset=offset)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid pending pagination must be rejected")

    boundary = queue.list_pending(OWNER, limit=10, offset=1_000_000_000)
    assert boundary["offset"] == 1_000_000_000
    assert boundary["items"] == []


def review_sample():
    return {
        "candidate_classification": "FOREIGN_FINANCIAL_INVESTMENT",
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
    assert review["reviewer_identity_status"] == "DECLARED_NOT_VERIFIED"
    assert review["professional_registration_verified"] is False
    listed = queue.list_reviews(OWNER, pending["pending_id"])[0]
    assert listed["review_id"] == review["review_id"]
    assert listed["professional_registration_verified"] is False
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


def test_review_rejects_non_text_identity_and_evidence_fields(tmp_path):
    queue = make_queue(tmp_path / "review-types.sqlite3")
    item = queue.add(OWNER, sample())
    for field in ("confirmed_jurisdiction", "reviewer_name", "reviewer_role",
                  "professional_registration", "evidence_reference"):
        payload = review_sample()
        payload[field] = ["texto", "indevido"]
        try:
            queue.record_review(OWNER, item["pending_id"], payload)
        except ValueError as exc:
            assert "deve ser texto" in str(exc)
        else:
            raise AssertionError(f"{field} must reject non-text values")

    try:
        queue.record_review(OWNER, 123, review_sample())
    except ValueError as exc:
        assert "pending_id inválido" in str(exc)
    else:
        raise AssertionError("non-text pending_id must be rejected")

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


def test_foreign_realized_profit_and_loss_keep_their_original_sign_and_stay_pending(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    profit = queue.add_realized_result(OWNER, {
        "reference": "FOREIGN-RESULT-PROFIT",
        "original_result": 125.75,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-03",
    })
    loss = queue.add_realized_result(OWNER, {
        "reference": "FOREIGN-RESULT-LOSS",
        "original_result": -42.25,
        "original_currency": "EUR",
        "instrument": "Forex",
        "jurisdiction": "EU",
        "occurred_on": "2026-11-03",
    })
    assert profit["original_result"] == 125.75
    assert profit["record_kind"] == "REALIZED_RESULT"
    assert loss["original_result"] == -42.25
    assert loss["original_amount"] == 42.25
    assert loss["record_kind"] == "REALIZED_RESULT"
    assert profit["status"] == loss["status"] == "PENDING_CLASSIFICATION"
    assert queue.list_pending(OWNER)["total"] == 2


def test_foreign_realized_result_rejects_boolean_and_non_finite_values(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for value in (True, float("inf"), float("-inf"), float("nan")):
        try:
            queue.add_realized_result(OWNER, {
                "reference": f"BAD-{value}",
                "original_result": value,
                "original_currency": "USD",
                "instrument": "ETF",
                "jurisdiction": "US",
                "occurred_on": "2026-11-03",
            })
        except ValueError:
            pass
        else:
            raise AssertionError("invalid signed result must be rejected")


def test_summary_counts_entire_queue_and_is_scoped_to_owner(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for number in range(501):
        queue.add_realized_result(OWNER, {
            "reference": f"SUMMARY-OWNER-A-{number}",
            "original_result": -1.0 if number % 2 else 2.0,
            "original_currency": "USD" if number % 2 else "EUR",
            "instrument": "Forex",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": "2026-11-03",
        })
    queue.add("another-owner", {
        **sample("SUMMARY-OWNER-B-ONLY"),
        "fx_rate": None,
        "fx_date": None,
        "fx_source": None,
        "fx_conversion_method": "NOT_INFORMED",
    })

    summary = queue.summary(OWNER, as_of=date(2026, 11, 3))
    assert summary == {
        "available": True,
        "as_of": "2026-11-03",
        "total": 501,
        "realized_results": 501,
        "asset_amounts": 0,
        "planning_estimates_registered": 0,
        "currencies": ["EUR", "USD"],
        "evidence_completeness": {
            "total": 501,
            "missing_institution": 501,
            "missing_custody_location": 501,
            "missing_contract_type": 501,
            "missing_core_evidence": 501,
        },
        "periods": {
            "day": {"start": "2026-11-03", "end": "2026-11-03", "total": 501, "realized_results": 501, "asset_amounts": 0},
            "week": {"start": "2026-11-02", "end": "2026-11-03", "total": 501, "realized_results": 501, "asset_amounts": 0},
            "month": {"start": "2026-11-01", "end": "2026-11-03", "total": 501, "realized_results": 501, "asset_amounts": 0},
            "year": {"start": "2026-01-01", "end": "2026-11-03", "total": 501, "realized_results": 501, "asset_amounts": 0},
        },
        "classification_status": "PENDING_CLASSIFICATION",
        "included_in_totals": False,
        "reserve_calculated": False,
    }
    other = queue.summary("another-owner")
    assert other["total"] == 1
    assert other["asset_amounts"] == 1
    assert other["realized_results"] == 0
    assert other["currencies"] == ["USD"]



def test_database_composite_foreign_key_blocks_cross_owner_review_links(tmp_path):
    import sqlite3

    queue = make_queue(tmp_path / "foreign-review-owner-fk.sqlite3")
    pending = queue.add(OWNER, sample("FOREIGN-OWNER-FK"))
    payload = review_sample()
    try:
        with queue._connect() as db:
            db.execute(
                """INSERT INTO fiscal_pending_reviews
                (review_id, owner_id, pending_id, candidate_classification,
                 confirmed_jurisdiction, reviewer_name, reviewer_role,
                 professional_registration, evidence_reference, reviewed_on,
                 review_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "cross-owner-review",
                    "different-owner",
                    pending["pending_id"],
                    payload["candidate_classification"],
                    payload["confirmed_jurisdiction"],
                    payload["reviewer_name"],
                    payload["reviewer_role"],
                    payload["professional_registration"],
                    payload["evidence_reference"],
                    payload["reviewed_on"],
                    payload["review_notes"],
                    "2026-11-06T12:00:00+00:00",
                ),
            )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError(
            "database composite foreign key must reject a review linked across owners"
        )

    assert queue.list_reviews(OWNER, pending["pending_id"]) == []

def test_review_cannot_attach_to_another_owners_pending_item(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    pending = queue.add(OWNER, sample())
    try:
        queue.record_review("different-owner", pending["pending_id"], review_sample())
    except ValueError as exc:
        assert "não encontrada" in str(exc)
    else:
        raise AssertionError("cross-owner review must be rejected")
    assert queue.list_reviews(OWNER, pending["pending_id"]) == []



def test_pending_period_counts_are_date_scoped_and_never_become_money_totals(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for day, kind, ref in (
        ("2026-10-31", "asset", "BEFORE-WEEK"),
        ("2026-11-02", "result", "THIS-WEEK-RESULT"),
        ("2026-11-03", "asset", "TODAY-ASSET"),
        ("2026-11-04", "result", "FUTURE-RESULT"),
    ):
        payload = sample(ref)
        payload["occurred_on"] = day
        if kind == "result":
            payload = {
                "reference": ref,
                "original_result": -12.0,
                "original_currency": "USD",
                "instrument": "ETF",
                "jurisdiction": "PENDING_REVIEW",
                "occurred_on": day,
            }
            queue.add_realized_result(OWNER, payload)
        else:
            queue.add(OWNER, payload)

    summary = queue.summary(OWNER, as_of=date(2026, 11, 3))
    assert summary["periods"]["day"]["total"] == 1
    assert summary["periods"]["day"]["asset_amounts"] == 1
    assert summary["periods"]["day"]["realized_results"] == 0
    assert summary["periods"]["week"]["total"] == 2
    assert summary["periods"]["month"]["total"] == 2
    assert summary["periods"]["year"]["total"] == 3
    assert summary["total"] == 4
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False
    assert "original_result" not in str(summary)


def test_foreign_queue_rejects_missing_owner_identity_for_every_operation(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = sample("OWNER-REQUIRED")
    for operation in (
        lambda: queue.add("", payload),
        lambda: queue.add_realized_result("", {
            "reference": "OWNER-REQUIRED-RESULT",
            "original_result": 1.0,
            "original_currency": "USD",
            "instrument": "ETF",
            "jurisdiction": "PENDING_REVIEW",
            "occurred_on": "2026-11-03",
        }),
        lambda: queue.list_pending(""),
        lambda: queue.summary(""),
        lambda: queue.list_reviews("", "missing"),
        lambda: queue.record_review("", "missing", review_sample()),
    ):
        try:
            operation()
        except ValueError as exc:
            assert "identidade proprietária" in str(exc)
        else:
            raise AssertionError("foreign queue operation must reject missing owner identity")


def test_foreign_pending_stores_structured_tax_and_event_declarations(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = sample("FOREIGN-STRUCTURED-EVIDENCE")
    payload.update({
        "tax_residency_at_event": "BRAZIL",
        "income_nature": "DIVIDEND",
        "event_type": "DIVIDEND_RECEIPT",
        "fx_conversion_method": "PTAX_SELL",
    })
    item = queue.add(OWNER, payload)
    assert item["tax_residency_at_event"] == "BRAZIL"
    assert item["income_nature"] == "DIVIDEND"
    assert item["event_type"] == "DIVIDEND_RECEIPT"
    assert item["fx_conversion_method"] == "PTAX_SELL"
    listed = queue.list_pending(OWNER)["items"][0]
    assert listed["tax_residency_at_event"] == "BRAZIL"
    assert listed["status"] == "PENDING_CLASSIFICATION"


def test_foreign_pending_structured_fields_default_to_unknown_and_reject_invalid_values(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    default_payload = sample("FOREIGN-DEFAULT-EVIDENCE")
    default_payload.update({
        "fx_rate": None,
        "fx_date": None,
        "fx_source": None,
        "fx_conversion_method": "NOT_INFORMED",
    })
    item = queue.add(OWNER, default_payload)
    assert item["tax_residency_at_event"] == "NOT_INFORMED"
    assert item["income_nature"] == "NOT_INFORMED"
    assert item["event_type"] == "NOT_INFORMED"
    assert item["fx_conversion_method"] == "NOT_INFORMED"
    for field, invalid in (
        ("tax_residency_at_event", "BRAZILIAN"),
        ("income_nature", "GENERIC_15_PERCENT"),
        ("event_type", "TAXABLE"),
        ("fx_conversion_method", "AUTOMATIC_GUESS"),
    ):
        payload = sample("INVALID-" + field)
        payload[field] = invalid
        try:
            queue.add(OWNER, payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid declaration must be rejected for {field}")


def test_foreign_realized_result_preserves_structured_declarations(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    result = queue.add_realized_result(OWNER, {
        "reference": "FOREIGN-RESULT-STRUCTURED",
        "original_result": -10.5,
        "original_currency": "EUR",
        "instrument": "ETF",
        "jurisdiction": "EU",
        "occurred_on": "2026-11-04",
        "tax_residency_at_event": "DUAL_OR_UNCERTAIN",
        "income_nature": "CAPITAL_GAIN",
        "event_type": "DISPOSAL",
        "fx_conversion_method": "BROKER_STATEMENT",
        "fx_rate": 5.8,
        "fx_date": "2026-11-04",
        "fx_source": "Extrato da corretora",
    })
    assert result["original_result"] == -10.5
    assert result["tax_residency_at_event"] == "DUAL_OR_UNCERTAIN"
    assert result["income_nature"] == "CAPITAL_GAIN"
    assert result["event_type"] == "DISPOSAL"
    assert result["fx_conversion_method"] == "BROKER_STATEMENT"
    assert result["status"] == "PENDING_CLASSIFICATION"


def test_foreign_structured_declarations_do_not_change_pending_summary_or_reserve_semantics(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = sample("FOREIGN-DECLARATION-NOT-TAX")
    payload.update({
        "tax_residency_at_event": "BRAZIL",
        "income_nature": "DIVIDEND",
        "event_type": "DIVIDEND_RECEIPT",
        "fx_conversion_method": "PTAX_SELL",
    })
    queue.add(OWNER, payload)
    summary = queue.summary(OWNER)
    assert summary["total"] == 1
    assert summary["asset_amounts"] == 1
    assert summary["realized_results"] == 0
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False
    assert "tax_residency_at_event" not in summary
    assert "income_nature" not in summary
    assert "event_type" not in summary
    assert "fx_conversion_method" not in summary


def test_not_converted_method_rejects_fx_quote_for_assets_and_realized_results(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    asset = sample("FOREIGN-NOT-CONVERTED-ASSET")
    asset["fx_conversion_method"] = "NOT_CONVERTED"
    realized = {
        "reference": "FOREIGN-NOT-CONVERTED-RESULT",
        "original_result": 25.75,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-03",
        "fx_rate": 5.42,
        "fx_date": "2026-11-03",
        "fx_source": "Fonte documental de teste",
        "fx_conversion_method": "NOT_CONVERTED",
    }

    for payload, add_item in (
        (asset, lambda value: queue.add(OWNER, value)),
        (realized, lambda value: queue.add_realized_result(OWNER, value)),
    ):
        try:
            add_item(payload)
        except ValueError as exc:
            assert "NOT_CONVERTED" in str(exc)
        else:
            raise AssertionError("NOT_CONVERTED must reject a supplied FX quote")

    assert queue.list_pending(OWNER)["total"] == 0


def test_foreign_review_rejects_non_text_notes_and_list_id(tmp_path):
    queue = make_queue(tmp_path / "strict-foreign-review.sqlite3")
    item = queue.add(OWNER, sample("FOREIGN-STRICT-REVIEW"))
    payload = review_sample()
    payload["review_notes"] = ["texto", "indevido"]
    try:
        queue.record_review(OWNER, item["pending_id"], payload)
    except ValueError as exc:
        assert "review_notes deve ser texto" in str(exc)
    else:
        raise AssertionError("review_notes must reject non-text values")

    try:
        queue.list_reviews(OWNER, 123)
    except ValueError as exc:
        assert "pending_id inválido" in str(exc)
    else:
        raise AssertionError("list_reviews must reject non-text pending_id")


def test_foreign_review_rejects_future_review_date(tmp_path):
    queue = make_queue(tmp_path / "future-foreign-review.sqlite3")
    item = queue.add(OWNER, sample("FOREIGN-FUTURE-REVIEW"))
    payload = review_sample()
    payload["reviewed_on"] = "9999-12-31"
    try:
        queue.record_review(OWNER, item["pending_id"], payload)
    except ValueError as exc:
        assert "reviewed_on não pode estar no futuro" in str(exc)
    else:
        raise AssertionError("future review dates must be rejected")
    assert queue.list_reviews(OWNER, item["pending_id"]) == []


def test_foreign_pending_rejects_non_text_intake_fields(tmp_path):
    queue = make_queue(tmp_path / "strict-foreign-intake.sqlite3")
    for field in (
        "reference", "instrument", "jurisdiction", "original_currency",
        "occurred_on", "fx_source", "notes", "income_nature",
    ):
        payload = sample("FOREIGN-STRICT-" + field.upper())
        payload[field] = ["valor", "indevido"]
        try:
            queue.add(OWNER, payload)
        except ValueError as exc:
            assert "deve ser texto" in str(exc)
        else:
            raise AssertionError(f"{field} must reject non-text values")
    assert queue.list_pending(OWNER)["total"] == 0


def test_foreign_realized_pending_rejects_non_text_intake_fields(tmp_path):
    queue = make_queue(tmp_path / "strict-foreign-realized.sqlite3")
    base = {
        "reference": "FOREIGN-STRICT-REALIZED",
        "original_result": 12.5,
        "original_currency": "EUR",
        "instrument": "ETF",
        "jurisdiction": "PENDING_REVIEW",
        "occurred_on": "2026-11-04",
    }
    for field in ("reference", "instrument", "jurisdiction", "original_currency", "occurred_on", "notes"):
        payload = {**base, field: ["valor", "indevido"]}
        try:
            queue.add_realized_result(OWNER, payload)
        except ValueError as exc:
            assert "deve ser texto" in str(exc)
        else:
            raise AssertionError(f"{field} must reject non-text realized values")
    assert queue.list_pending(OWNER)["total"] == 0


def test_foreign_pending_rejects_coerced_or_nonfinite_numeric_values(tmp_path):
    import pytest
    queue = make_queue(tmp_path / "strict-foreign-money.sqlite3")
    for field in ("original_amount", "fx_rate"):
        for value in ("5.42", True, [], {}, float("nan"), float("inf")):
            payload = sample("FOREIGN-STRICT-" + field + str(type(value).__name__) + str(value)[:5])
            payload[field] = value
            try:
                queue.add(OWNER, payload)
            except ValueError as exc:
                assert field in str(exc)
            else:
                raise AssertionError(f"{field} must reject coerced or non-finite values")
    base = {
        "reference": "FOREIGN-STRICT-RESULT-NUMERIC",
        "original_result": 12.5,
        "original_currency": "EUR",
        "instrument": "ETF",
        "jurisdiction": "PENDING_REVIEW",
        "occurred_on": "2026-11-04",
    }
    for value in ("12.5", True, [], {}, float("nan"), float("inf")):
        payload = {**base, "original_result": value}
        try:
            queue.add_realized_result(OWNER, payload)
        except ValueError as exc:
            assert "original_result" in str(exc)
        else:
            raise AssertionError("original_result must reject coerced or non-finite values")
    assert queue.list_pending(OWNER)["total"] == 0


def test_foreign_pending_rejects_out_of_range_pagination_offsets(tmp_path):
    queue = make_queue(tmp_path / "foreign-pagination-bounds.sqlite3")
    queue.add(OWNER, sample("FOREIGN-PAGE-BOUNDARY"))

    for offset in (-1, True, 1_000_000_001, 2**63):
        try:
            queue.list_pending(OWNER, limit=10, offset=offset)
        except ValueError as exc:
            assert "offset" in str(exc)
        else:
            raise AssertionError("out-of-range foreign pending offset must be rejected")

    page = queue.list_pending(OWNER, limit=10, offset=1_000_000_000)
    assert page["offset"] == 1_000_000_000
    assert page["items"] == []
    assert page["total"] == 1


def test_foreign_reference_uniqueness_is_scoped_to_owner(tmp_path):
    queue = make_queue(tmp_path / "foreign-owner-reference.sqlite3")
    reference = "SAME-BROKER-REFERENCE"
    queue.add("owner-a", sample(reference))
    queue.add("owner-b", sample(reference))

    owner_a = queue.list_pending("owner-a")
    owner_b = queue.list_pending("owner-b")
    assert owner_a["total"] == owner_b["total"] == 1
    assert owner_a["items"][0]["reference"] == reference
    assert owner_b["items"][0]["reference"] == reference


def test_foreign_pending_rejects_non_text_owner_identity(tmp_path):
    import pytest

    queue = make_queue(tmp_path / "strict-foreign-owner.sqlite3")
    for invalid_owner in (None, 123, True, [], {}, object()):
        with pytest.raises(ValueError, match="identidade proprietária"):
            queue.list_pending(invalid_owner)


def test_foreign_queue_accepts_currency_codes_outside_old_fixed_list(tmp_path):
    queue = make_queue(tmp_path / "fiscal-open-currency.sqlite3")
    payload = sample("FOREIGN-CURRENCY-OPEN")
    payload["original_currency"] = "NZD"
    item = queue.add(OWNER, payload)
    assert item["original_currency"] == "NZD"


def test_foreign_queue_rejects_malformed_currency_codes(tmp_path):
    queue = make_queue(tmp_path / "fiscal-invalid-currency.sqlite3")
    for code in ("US", "US1", "USDD", "ÄBC", "   "):
        payload = sample("BAD-CURRENCY-" + str(len(code)) + "-" + code.encode("utf-8").hex())
        payload["original_currency"] = code
        try:
            queue.add(OWNER, payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed currency code must be rejected: {code!r}")

def test_foreign_realized_result_accepts_currency_outside_old_fixed_list(tmp_path):
    queue = make_queue(tmp_path / "fiscal-open-realized-currency.sqlite3")
    result = queue.add_realized_result(OWNER, {
        "reference": "FOREIGN-RESULT-NZD",
        "original_result": 18.25,
        "original_currency": "NZD",
        "instrument": "ETF",
        "jurisdiction": "NZ",
        "occurred_on": "2026-11-06",
    })
    assert result["original_currency"] == "NZD"
    assert result["status"] == "PENDING_CLASSIFICATION"


def test_foreign_realized_result_rejects_malformed_currency_codes(tmp_path):
    queue = make_queue(tmp_path / "fiscal-invalid-realized-currency.sqlite3")
    for code in ("US", "US1", "USDD", "ÄBC", "   "):
        try:
            queue.add_realized_result(OWNER, {
                "reference": "BAD-RESULT-CURRENCY-" + code.encode("utf-8").hex(),
                "original_result": 1.0,
                "original_currency": code,
                "instrument": "ETF",
                "jurisdiction": "PENDING_REVIEW",
                "occurred_on": "2026-11-06",
            })
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed realized currency code must be rejected: {code!r}")




def test_foreign_pending_persists_institution_custody_contract_and_cost_evidence(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = sample("FOREIGN-STRUCTURED-001")
    payload.update({
        "institution": "Broker International",
        "custody_location": "Custódia em instituição estrangeira",
        "contract_type": "ETF à vista",
        "acquisition_cost": 100.25,
        "transaction_fees": 2.5,
        "foreign_tax_paid": 1.75,
    })

    item = queue.add(OWNER, payload)
    stored = queue.list_pending(OWNER)["items"][0]

    assert item["institution"] == stored["institution"] == "Broker International"
    assert stored["custody_location"] == "Custódia em instituição estrangeira"
    assert stored["contract_type"] == "ETF à vista"
    assert stored["acquisition_cost"] == 100.25
    assert stored["transaction_fees"] == 2.5
    assert stored["foreign_tax_paid"] == 1.75
    assert stored["status"] == "PENDING_CLASSIFICATION"


def test_foreign_realized_result_persists_structured_evidence_without_calculation(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    payload = {
        "reference": "FOREIGN-REALIZED-STRUCTURED",
        "original_result": -125.5,
        "original_currency": "EUR",
        "instrument": "FUTURES",
        "jurisdiction": "US",
        "occurred_on": "2026-11-05",
        "institution": "Broker EU",
        "custody_location": "Custódia estrangeira",
        "contract_type": "Contrato futuro",
        "acquisition_cost": 1000,
        "transaction_fees": 4.5,
        "foreign_tax_paid": 0,
    }

    item = queue.add_realized_result(OWNER, payload)
    stored = queue.list_pending(OWNER)["items"][0]

    assert item["record_kind"] == stored["record_kind"] == "REALIZED_RESULT"
    assert stored["original_result"] == -125.5
    assert stored["institution"] == "Broker EU"
    assert stored["contract_type"] == "Contrato futuro"
    assert stored["acquisition_cost"] == 1000
    assert stored["transaction_fees"] == 4.5
    assert stored["foreign_tax_paid"] == 0
    assert stored["status"] == "PENDING_CLASSIFICATION"
    assert queue.summary(OWNER)["included_in_totals"] is False


def test_optional_foreign_cost_fields_reject_negative_boolean_and_non_finite_values(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    for field, value in (
        ("acquisition_cost", -1),
        ("transaction_fees", True),
        ("foreign_tax_paid", float("inf")),
    ):
        payload = sample("INVALID-COST-" + field)
        payload[field] = value
        try:
            queue.add(OWNER, payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {field} must be rejected")



def test_foreign_pending_summary_reports_only_aggregate_missing_core_evidence(tmp_path):
    queue = make_queue(tmp_path / "fiscal.sqlite3")
    queue.add(OWNER, sample("EVIDENCE-COMPLETE-01") | {
        "institution": "Broker A",
        "custody_location": "Foreign custodian",
        "contract_type": "ETF",
    })
    queue.add(OWNER, sample("EVIDENCE-MISSING-02") | {
        "institution": "Broker B",
        "custody_location": "NOT_INFORMED",
        "contract_type": "NOT_CONFIRMED",
    })
    queue.add(OWNER, sample("EVIDENCE-SELF-CUSTODY-03") | {
        "institution": "",
        "custody_location": "Autocustódia própria",
        "contract_type": "Spot",
    })

    summary = queue.summary(OWNER)

    assert summary["evidence_completeness"] == {
        "total": 3,
        "missing_institution": 0,
        "missing_custody_location": 1,
        "missing_contract_type": 1,
        "missing_core_evidence": 1,
    }
    assert summary["included_in_totals"] is False
    assert summary["reserve_calculated"] is False
    assert "reference" not in summary["evidence_completeness"]



def test_foreign_queue_rejects_future_event_and_fx_dates_for_assets_and_results(tmp_path):
    queue = make_queue(tmp_path / "future-dates.sqlite3")
    tomorrow = (
        datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=1)
    ).isoformat()

    asset = sample("FUTURE-ASSET-EVENT")
    asset["occurred_on"] = tomorrow
    try:
        queue.add(OWNER, asset)
    except ValueError as exc:
        assert "occurred_on não pode estar no futuro" in str(exc)
    else:
        raise AssertionError("future foreign asset event date must be rejected")

    asset = sample("FUTURE-ASSET-FX")
    asset["fx_date"] = tomorrow
    try:
        queue.add(OWNER, asset)
    except ValueError as exc:
        assert "fx_date não pode estar no futuro" in str(exc)
    else:
        raise AssertionError("future FX evidence date must be rejected")

    realized = {
        "reference": "FUTURE-REALIZED-EVENT",
        "original_result": 10.0,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": tomorrow,
    }
    try:
        queue.add_realized_result(OWNER, realized)
    except ValueError as exc:
        assert "occurred_on não pode estar no futuro" in str(exc)
    else:
        raise AssertionError("future realized result date must be rejected")

    realized["reference"] = "FUTURE-REALIZED-FX"
    realized["occurred_on"] = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    realized.update({
        "fx_rate": 5.0,
        "fx_date": tomorrow,
        "fx_source": "fonte documental",
        "fx_conversion_method": "PTAX_SELL",
    })
    try:
        queue.add_realized_result(OWNER, realized)
    except ValueError as exc:
        assert "fx_date não pode estar no futuro" in str(exc)
    else:
        raise AssertionError("future FX evidence date on realized result must be rejected")


def test_fx_conversion_method_must_match_quote_evidence_for_assets_and_results(tmp_path):
    queue = make_queue(tmp_path / "fx-method-consistency.sqlite3")

    asset_missing_method = sample("FX-ASSET-MISSING-METHOD")
    asset_missing_method.pop("fx_conversion_method")
    realized_missing_method = {
        "reference": "FX-RESULT-MISSING-METHOD",
        "original_result": 10.0,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-03",
        "fx_rate": 5.0,
        "fx_date": "2026-11-03",
        "fx_source": "Extrato de teste",
    }

    asset_method_without_quote = {
        **sample("FX-ASSET-METHOD-WITHOUT-QUOTE"),
        "fx_rate": None,
        "fx_date": None,
        "fx_source": None,
        "fx_conversion_method": "PTAX_SELL",
    }
    realized_method_without_quote = {
        "reference": "FX-RESULT-METHOD-WITHOUT-QUOTE",
        "original_result": 10.0,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-11-03",
        "fx_conversion_method": "PTAX_SELL",
    }

    for payload, add_item, expected in (
        (asset_missing_method, lambda value: queue.add(OWNER, value), "deve ser informado"),
        (realized_missing_method, lambda value: queue.add_realized_result(OWNER, value), "deve ser informado"),
        (asset_method_without_quote, lambda value: queue.add(OWNER, value), "exige fx_rate"),
        (realized_method_without_quote, lambda value: queue.add_realized_result(OWNER, value), "exige fx_rate"),
    ):
        try:
            add_item(payload)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("FX method and quote evidence must be mutually consistent")

    assert queue.list_pending(OWNER)["total"] == 0


def test_foreign_review_history_is_append_only_at_database_level(tmp_path):
    import sqlite3

    queue = make_queue(tmp_path / "append-only-foreign-review.sqlite3")
    pending = queue.add(OWNER, sample("FOREIGN-APPEND-ONLY"))
    review = queue.record_review(OWNER, pending["pending_id"], review_sample())

    for statement, params in (
        ("UPDATE fiscal_pending_reviews SET reviewer_name = 'alterado' WHERE review_id = ?", (review["review_id"],)),
        ("DELETE FROM fiscal_pending_reviews WHERE review_id = ?", (review["review_id"],)),
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            with queue._connect() as db:
                db.execute(statement, params)

    history = queue.list_reviews(OWNER, pending["pending_id"])
    assert len(history) == 1
    assert history[0]["reviewer_name"] == review["reviewer_name"]
