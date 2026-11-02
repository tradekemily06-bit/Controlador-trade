from finance.fiscal_reserve import FiscalReserve


def test_defaults_are_separate_and_configurable(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    assert reserve.settings() == {
        "BR_DAY_TRADE": 20.0,
        "FOREIGN_FINANCIAL_ASSET": 15.0,
    }
    reserve.update_rate("BR_DAY_TRADE", 18)
    assert reserve.settings()["BR_DAY_TRADE"] == 18.0


def test_brazil_result_is_reserved_and_generic_foreign_result_is_blocked(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    brazil = reserve.record_realized_result({
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "MT5-DEMO-TRADE-001",
        "occurred_on": "2026-10-29",
    })
    assert brazil["reserve_amount_brl"] == 200
    try:
        reserve.record_realized_result({
            "category": "FOREIGN_FINANCIAL_ASSET",
            "realized_result_brl": 2000,
            "reference": "BROKER-STATEMENT-001",
            "occurred_on": "2026-10-29",
        })
    except ValueError as exc:
        assert "classificação tributária" in str(exc)
    else:
        raise AssertionError("generic foreign results must remain unreserved")
    summary = reserve.summary()
    assert summary["total_reserved_brl"] == 200
    assert summary["categories"]["BR_DAY_TRADE"]["reserve_amount_brl"] == 200
    assert summary["categories"]["FOREIGN_FINANCIAL_ASSET"]["reserve_amount_brl"] == 0
    assert len(summary["history"]) == 1


def test_losses_are_recorded_without_assuming_tax_loss_offsets(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    entry = reserve.record_realized_result({
        "category": "BR_DAY_TRADE",
        "realized_result_brl": -250,
        "reference": "TRADE-LOSS-001",
    })
    assert entry["realized_result_brl"] == -250
    assert entry["reserve_amount_brl"] == 0
    assert reserve.summary()["categories"]["BR_DAY_TRADE"]["realized_result_brl"] == -250


def test_unknown_foreign_classification_is_rejected(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    try:
        reserve.record_realized_result({
            "category": "FOREIGN_CFD_UNCLASSIFIED",
            "realized_result_brl": 100,
            "reference": "FOREIGN-001",
        })
    except ValueError as exc:
        assert "categoria" in str(exc)
    else:
        raise AssertionError("unclassified foreign category must be rejected")


def test_reference_is_required_and_percent_is_bounded(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    try:
        reserve.record_realized_result({
            "category": "BR_DAY_TRADE",
            "realized_result_brl": 100,
        })
    except ValueError as exc:
        assert "reference" in str(exc)
    else:
        raise AssertionError("reference must be required")
    try:
        reserve.update_rate("BR_DAY_TRADE", 101)
    except ValueError as exc:
        assert "entre 0 e 100" in str(exc)
    else:
        raise AssertionError("rate above 100 must be rejected")



def test_duplicate_reference_is_rejected_without_double_reserving(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    payload = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "CYCLE-UNIQUE-001",
    }
    reserve.record_realized_result(payload)
    try:
        reserve.record_realized_result(payload)
    except ValueError as exc:
        assert "já foi registrada" in str(exc)
    else:
        raise AssertionError("duplicate reference must not be counted twice")
    assert reserve.summary()["total_reserved_brl"] == 200


def test_only_brazil_rate_can_be_updated_and_invalid_set_changes_nothing(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    reserve.update_rates({"BR_DAY_TRADE": 19})
    assert reserve.settings() == {
        "BR_DAY_TRADE": 19.0,
        "FOREIGN_FINANCIAL_ASSET": 15.0,
    }
    for attempt in (
        lambda: reserve.update_rate("FOREIGN_FINANCIAL_ASSET", 14),
        lambda: reserve.update_rates({"BR_DAY_TRADE": 18, "FOREIGN_FINANCIAL_ASSET": 14}),
    ):
        try:
            attempt()
        except ValueError:
            pass
        else:
            raise AssertionError("generic foreign rate changes must be rejected")
    try:
        reserve.update_rates({"BR_DAY_TRADE": 101})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid Brazilian rate must be rejected")
    assert reserve.settings() == {
        "BR_DAY_TRADE": 19.0,
        "FOREIGN_FINANCIAL_ASSET": 15.0,
    }


def test_summary_exposes_day_week_month_and_year_totals(tmp_path):
    from datetime import date

    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    records = [
        ("2026-10-30", 100, "TODAY"),
        ("2026-10-28", 200, "THIS-WEEK"),
        ("2026-10-01", 300, "THIS-MONTH"),
        ("2026-09-30", 400, "THIS-YEAR"),
        ("2025-12-31", 500, "LAST-YEAR"),
    ]
    for occurred_on, amount, reference in records:
        reserve.record_realized_result({
            "category": "BR_DAY_TRADE",
            "realized_result_brl": amount,
            "reference": reference,
            "occurred_on": occurred_on,
        })

    summary = reserve.summary(as_of=date(2026, 10, 30))
    assert set(summary["periods"]) == {"day", "week", "month", "year"}
    assert summary["periods"]["day"]["realized_result_brl"] == 100
    assert summary["periods"]["day"]["reserve_amount_brl"] == 20
    assert summary["periods"]["week"]["realized_result_brl"] == 300
    assert summary["periods"]["month"]["realized_result_brl"] == 600
    assert summary["periods"]["year"]["realized_result_brl"] == 1000


def test_date_must_be_exact_iso_calendar_date(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    for invalid in ("20261030", "30-10-2026", "2026-02-30"):
        try:
            reserve.record_realized_result({
                "category": "BR_DAY_TRADE",
                "realized_result_brl": 100,
                "reference": "INVALID-" + invalid,
                "occurred_on": invalid,
            })
        except ValueError as exc:
            assert "YYYY-MM-DD" in str(exc)
        else:
            raise AssertionError("non-ISO or invalid calendar date must be rejected")


def test_default_in_memory_database_persists_between_operations():
    reserve = FiscalReserve()
    assert reserve.settings()["BR_DAY_TRADE"] == 20.0
    entry = reserve.record_realized_result({
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 100,
        "reference": "MEMORY-DB-001",
    })
    assert entry["reserve_amount_brl"] == 20
    assert reserve.summary()["total_reserved_brl"] == 20



def test_history_pagination_returns_total_and_has_more(tmp_path):
    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    for number in range(5):
        reserve.record_realized_result({
            "category": "BR_DAY_TRADE",
            "realized_result_brl": 100 + number,
            "reference": f"PAGE-{number}",
            "occurred_on": "2026-10-30",
        })
    first = reserve.summary(history_limit=2, history_offset=0)
    second = reserve.summary(history_limit=2, history_offset=2)
    last = reserve.summary(history_limit=2, history_offset=4)
    assert first["history_page"] == {"limit": 2, "offset": 0, "returned": 2, "total": 5, "has_more": True}
    assert second["history_page"]["has_more"] is True
    assert last["history_page"]["has_more"] is False
    assert len({row["reference"] for row in first["history"] + second["history"] + last["history"]}) == 5


def test_concurrent_duplicate_reference_is_never_double_recorded(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    reserve = FiscalReserve(str(tmp_path / "fiscal.sqlite3"))
    payload = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "CONCURRENT-UNIQUE-001",
    }

    def attempt():
        try:
            reserve.record_realized_result(payload)
            return "created"
        except ValueError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: attempt(), range(8)))

    assert results.count("created") == 1
    assert results.count("duplicate") == 7
    assert reserve.summary()["total_reserved_brl"] == 200
