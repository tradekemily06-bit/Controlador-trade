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
    queue.add("owner-a", sample())
    migrate_fiscal_schema(path)
    reserve = FiscalReserve(path)

    assert queue.list_pending("owner-a")["total"] == 1
    assert reserve.summary("owner-a")["total_reserved_brl"] == 0


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

def test_domestic_pending_supports_shared_in_memory_database():
    queue = FiscalDomesticPendingQueue()
    queue.add("owner-a", sample())
    assert queue.list_pending("owner-a")["total"] == 1
