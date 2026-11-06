import os
from datetime import date
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_schema import migrate_fiscal_schema

os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "test-owner"
from finance.fiscal_identity import configured_fiscal_owner_id
OWNER = configured_fiscal_owner_id()

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
    for limit, offset in ((0, 0), (501, 0), (True, 0), (10, -1), (10, True), (10, 1_000_000_001), (10, 2**63)):
        try:
            queue.list_pending(OWNER, limit=limit, offset=offset)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid pending pagination must be rejected")


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
    })

    summary = queue.summary(OWNER, as_of=date(2026, 11, 3))
    assert summary == {
        "available": True,
        "as_of": "2026-11-03",
        "total": 501,
        "realized_results": 501,
        "asset_amounts": 0,
        "currencies": ["EUR", "USD"],
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
    item = queue.add(OWNER, sample("FOREIGN-DEFAULT-EVIDENCE"))
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
