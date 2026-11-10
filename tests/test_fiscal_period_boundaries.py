from __future__ import annotations

from datetime import date

from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema


def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "fiscal-period-owner@example.com")
    database = tmp_path / "fiscal-periods.sqlite3"
    owner_id = migrate_fiscal_schema(str(database))
    return owner_id, FiscalReserve(str(database))


def _record(store, owner_id, reference, occurred_on, amount=100.0):
    return store.record_realized_result(
        owner_id,
        {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": amount,
            "reference": reference,
            "occurred_on": occurred_on,
        },
    )


def test_summary_periods_use_inclusive_local_calendar_dates_and_exclude_prior_periods(tmp_path, monkeypatch):
    owner_id, store = _store(tmp_path, monkeypatch)
    # 10 Nov 2026 is Tuesday. The reporting week starts Monday 9 Nov.
    _record(store, owner_id, "year-boundary-before", "2025-12-31", 10)
    _record(store, owner_id, "year-boundary-start", "2026-01-01", 20)
    _record(store, owner_id, "month-boundary-before", "2026-10-31", 30)
    _record(store, owner_id, "month-boundary-start", "2026-11-01", 40)
    _record(store, owner_id, "week-boundary-before", "2026-11-08", 50)
    _record(store, owner_id, "week-boundary-start", "2026-11-09", 60)
    _record(store, owner_id, "day-boundary-before", "2026-11-09", 70)
    _record(store, owner_id, "day-boundary-start", "2026-11-10", 80)

    summary = store.summary(owner_id, as_of=date(2026, 11, 10))
    periods = summary["periods"]

    assert periods["day"] == {
        "start": "2026-11-10",
        "end": "2026-11-10",
        "entries": 1,
        "realized_result_brl": 80.0,
        "reserve_amount_brl": 16.0,
    }
    assert periods["week"]["start"] == "2026-11-09"
    assert periods["week"]["end"] == "2026-11-10"
    assert periods["week"]["entries"] == 1
    assert periods["week"]["realized_result_brl"] == 60.0
    assert periods["month"]["start"] == "2026-11-01"
    assert periods["month"]["entries"] == 2
    assert periods["month"]["realized_result_brl"] == 120.0
    assert periods["year"]["start"] == "2026-01-01"
    assert periods["year"]["entries"] == 4
    assert periods["year"]["realized_result_brl"] == 200.0


def test_summary_periods_handle_leap_day_and_year_end_without_date_overflow(tmp_path, monkeypatch):
    owner_id, store = _store(tmp_path, monkeypatch)
    _record(store, owner_id, "leap-day", "2024-02-29", 29)
    _record(store, owner_id, "leap-month-end", "2024-02-01", 1)
    _record(store, owner_id, "leap-year-start", "2024-01-01", 10)
    _record(store, owner_id, "year-end-before", "2023-12-31", 100)

    summary = store.summary(owner_id, as_of=date(2024, 2, 29))
    assert summary["periods"]["day"]["entries"] == 1
    assert summary["periods"]["day"]["realized_result_brl"] == 29.0
    assert summary["periods"]["month"]["entries"] == 2
    assert summary["periods"]["month"]["realized_result_brl"] == 30.0
    assert summary["periods"]["year"]["entries"] == 3
    assert summary["periods"]["year"]["realized_result_brl"] == 40.0
